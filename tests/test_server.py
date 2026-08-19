"""Endpoint behavior through FastAPI's TestClient. No network, rag mocked."""

import json

import pytest
from fastapi.testclient import TestClient

import auth
import conversations
import rag
import rate_limit
import server
import vector_store

USER = {"id": "user-123", "name": "Om Wani"}


@pytest.fixture
def client(monkeypatch):
    rate_limit.reset()
    conversations.reset()
    auth.clear_cache()
    monkeypatch.setattr(vector_store, "count", lambda: 21)
    monkeypatch.setattr(server.vector_store, "count", lambda: 21)
    with TestClient(server.app) as c:
        yield c
    rate_limit.reset()
    conversations.reset()


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setattr(server.auth, "verify_token", lambda token: USER)
    return {"Authorization": "Bearer good-token"}


@pytest.fixture
def canned_answer(monkeypatch):
    calls = {}

    def fake_stream(question, **kwargs):
        calls.update(kwargs, question=question)
        yield {"type": "sources", "sources": ["work item 1"]}
        yield {"type": "token", "text": "An "}
        yield {"type": "token", "text": "answer."}
        yield {"type": "done", "usage": {"prompt_tokens": 10, "completion_tokens": 2}}

    monkeypatch.setattr(server.rag, "answer_stream", fake_stream)
    return calls


def frames(response):
    return [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_health_needs_no_auth(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "vectors": 21}


def test_health_reports_an_empty_index(client, monkeypatch):
    monkeypatch.setattr(server.vector_store, "count", lambda: 0)
    assert client.get("/api/health").json()["status"] == "empty"


def test_chat_requires_authentication(client):
    response = client.post("/api/v1/chat", json={"question": "hi"})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"


def test_rejected_token_returns_the_documented_error_shape(client, monkeypatch):
    def reject(token):
        raise auth.AuthError()

    monkeypatch.setattr(server.auth, "verify_token", reject)

    response = client.post(
        "/api/v1/chat", json={"question": "hi"}, headers={"Authorization": "Bearer stale"}
    )

    assert response.status_code == 401
    assert set(response.json()) == {"error", "message"}


def test_streamed_answer_frames(client, signed_in, canned_answer):
    response = client.post(
        "/api/v1/chat", json={"question": "what is blocking auth?"}, headers=signed_in
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = frames(response)
    assert [e["type"] for e in events] == ["sources", "token", "token", "done"]
    assert events[0]["sources"] == ["work item 1"]


def test_work_item_id_is_passed_through_as_the_pin(client, signed_in, canned_answer):
    client.post(
        "/api/v1/chat", json={"question": "status?", "work_item_id": 13}, headers=signed_in
    )
    assert canned_answer["pin_work_item"] == 13


def test_missing_question_is_a_400(client, signed_in):
    response = client.post("/api/v1/chat", json={}, headers=signed_in)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_whitespace_only_question_is_a_400(client, signed_in):
    response = client.post("/api/v1/chat", json={"question": "   "}, headers=signed_in)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_oversized_question_is_a_400(client, signed_in):
    response = client.post("/api/v1/chat", json={"question": "x" * 5000}, headers=signed_in)
    assert response.status_code == 400


def test_empty_index_returns_503(client, signed_in, monkeypatch):
    monkeypatch.setattr(server.vector_store, "count", lambda: 0)
    response = client.post("/api/v1/chat", json={"question": "hi"}, headers=signed_in)
    assert response.status_code == 503
    assert response.json()["error"] == "not_indexed"


def test_rate_limit_returns_429_with_retry_after(client, signed_in, canned_answer):
    for _ in range(rate_limit.MAX_REQUESTS):
        client.post("/api/v1/chat", json={"question": "hi"}, headers=signed_in)

    response = client.post("/api/v1/chat", json={"question": "hi"}, headers=signed_in)

    assert response.status_code == 429
    assert response.json()["error"] == "rate_limited"
    assert int(response.headers["Retry-After"]) > 0


def test_conversation_history_is_recorded_and_replayed(client, signed_in, canned_answer):
    client.post(
        "/api/v1/chat",
        json={"question": "first", "conversation_id": "c1"},
        headers=signed_in,
    )

    assert conversations.get("c1") == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "An answer."},
    ]

    client.post(
        "/api/v1/chat",
        json={"question": "second", "conversation_id": "c1"},
        headers=signed_in,
    )

    assert canned_answer["history"][0]["content"] == "first"


def test_generation_failure_is_reported_inside_the_stream(client, signed_in, monkeypatch):
    def explode(question, **kwargs):
        yield {"type": "sources", "sources": []}
        raise RuntimeError("azure returned 500 for deployment gpt-4.1-mini")

    monkeypatch.setattr(server.rag, "answer_stream", explode)

    response = client.post("/api/v1/chat", json={"question": "hi"}, headers=signed_in)

    # Headers are long gone, so the failure has to ride the stream, not a status code.
    assert response.status_code == 200
    events = frames(response)
    assert events[-1]["type"] == "error"
    assert "azure" not in json.dumps(events[-1]).lower()


def test_failed_generation_is_not_recorded_as_history(client, signed_in, monkeypatch):
    def explode(question, **kwargs):
        yield {"type": "sources", "sources": []}
        raise RuntimeError("boom")

    monkeypatch.setattr(server.rag, "answer_stream", explode)

    client.post(
        "/api/v1/chat", json={"question": "hi", "conversation_id": "c2"}, headers=signed_in
    )

    assert conversations.get("c2") == []
