"""FastAPI backend for the DevOps Pilot work item widget.

    uvicorn server:app --reload

Endpoints live under /api and return JSON. The chat endpoint streams server-sent
events so the widget can render tokens as they arrive.
"""

import json
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

import auth
import conversations
import rag
import rate_limit
import vector_store

load_dotenv()

# Dev-only escape so the API can be exercised with curl before the extension
# exists. Never set this outside local development: it removes authentication
# entirely and leaves the Azure OpenAI key billable by anyone who can reach the
# port.
AUTH_DEV_BYPASS = os.getenv("AUTH_DEV_BYPASS") == "1"

@asynccontextmanager
async def lifespan(_app):
    if AUTH_DEV_BYPASS:
        print("WARNING: AUTH_DEV_BYPASS=1 - the chat endpoint is unauthenticated.")
    yield


app = FastAPI(title="DevOps Pilot", version="1.0.0", lifespan=lifespan)

# The widget runs in a sandboxed iframe served from a gallery CDN host derived
# from the publisher id. Read the exact origin off browser devtools on first
# load and put it in ALLOWED_ORIGINS.
origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["https://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


def error(status, code, message):
    """The one error shape every endpoint returns. Never raw exception text."""
    return JSONResponse(status_code=status, content={"error": code, "message": message})


@app.get("/api/health")
def health():
    """Readiness for the deploy probe. No auth: it exposes nothing but a count."""
    vectors = vector_store.count()
    return {"status": "ok" if vectors else "empty", "vectors": vectors}


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    work_item_id: int | None = None
    conversation_id: str | None = Field(default=None, max_length=100)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value):
        # min_length counts characters, so "   " would otherwise pass.
        stripped = value.strip()
        if not stripped:
            raise ValueError("question cannot be blank")
        return stripped


def identify(authorization):
    """Resolve the caller, or raise AuthError."""
    if AUTH_DEV_BYPASS:
        return {"id": "dev", "name": "Local development"}
    return auth.verify_token(auth.bearer_token(authorization))


def sse(event):
    """Encode one event as an SSE frame."""
    return f"data: {json.dumps(event)}\n\n"


def stream_answer(body, user):
    """Yield SSE frames for one question, recording the exchange when it completes."""
    collected = []
    try:
        for event in rag.answer_stream(
            body.question,
            pin_work_item=body.work_item_id,
            history=conversations.get(body.conversation_id),
        ):
            if event["type"] == "token":
                collected.append(event["text"])
            yield sse(event)
    except Exception:
        # The response headers went out long ago, so a status code is no longer
        # available. Report the failure inside the stream instead.
        yield sse({"type": "error", "error": "generation_failed",
                   "message": "The answer could not be generated. Try again."})
        return

    conversations.append(body.conversation_id, body.question, "".join(collected))


@app.post("/api/v1/chat")
async def chat(request: Request, authorization: str = Header(default="")):
    try:
        user = identify(authorization)
    except auth.AuthError as exc:
        return error(401, "unauthenticated", exc.message)

    try:
        rate_limit.check(user["id"])
    except rate_limit.RateLimited as exc:
        response = error(429, "rate_limited", exc.message)
        response.headers["Retry-After"] = str(exc.retry_after)
        return response

    try:
        body = ChatRequest(**await request.json())
    except Exception:
        return error(400, "invalid_request", "Send a JSON body with a 'question' field.")

    if vector_store.count() == 0:
        return error(503, "not_indexed", "The project content has not been indexed yet.")

    return StreamingResponse(
        stream_answer(body, user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
