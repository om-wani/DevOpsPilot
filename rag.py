"""Retrieve matching chunks and answer a question from them."""

import cost_log
import embeddings
import vector_store
from llm_client import chat_deployment, get_client

TOP_N = 8
CHUNK_LIMIT = 5

# Prior turns kept in the prompt. Older turns fall off so the prompt stays in budget.
MAX_HISTORY_TURNS = 6

SYSTEM_PROMPT = """You answer questions about an Azure DevOps project.

Answer only from the context provided. If the context does not contain the
answer, say so plainly and do not guess. Cite the source of every claim using
the source label shown in the context, for example [work item 3] or
[wiki: Setup Guide]. Be direct and brief."""


def select_chunks(results, limit=CHUNK_LIMIT):
    """Rank retrieved chunks and cut to the limit so the prompt stays in budget.

    Closest first. Ties break on chunk id so the same question gives the same
    context every time. An empty result set returns an empty list.
    """
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if not results:
        return []

    ranked = sorted(results, key=lambda r: (r.get("distance", 0.0), r.get("id", "")))
    return ranked[:limit]


def source_label(metadata):
    """Human-readable citation label for a chunk."""
    if metadata.get("source_type") == "wiki":
        return f"wiki: {metadata.get('title', metadata.get('source_id', ''))}"
    return f"work item {metadata.get('source_id', '')}"


def build_context(chunks):
    """Format selected chunks for the prompt, each tagged with its source label."""
    return "\n\n---\n\n".join(
        f"[{source_label(c['metadata'])}]\n{c['text']}" for c in chunks
    )


def pin_first(chunks, pinned, limit=CHUNK_LIMIT):
    """Put `pinned` at the head of `chunks`, without exceeding `limit`.

    The chunk for the work item the user has open belongs in the context even
    when it is not the closest vector match, because the question is usually
    about it. Anything already retrieved is moved rather than duplicated.
    """
    if pinned is None:
        return chunks[:limit]

    rest = [c for c in chunks if c["id"] != pinned["id"]]
    return ([pinned] + rest)[:limit]


def retrieve(question, top_n=TOP_N, limit=CHUNK_LIMIT, where=None, pin_work_item=None):
    """Embed the question and return the chunks that should go into the prompt.

    `pin_work_item` is a work item id whose own chunk is forced into the context.
    """
    vector = embeddings.embed_query(question)
    chunks = select_chunks(vector_store.query(vector, top_n=top_n, where=where), limit)

    if pin_work_item is None:
        return chunks

    pinned = vector_store.get_chunk(f"work_item:{pin_work_item}:0")
    return pin_first(chunks, pinned, limit)


def build_messages(question, chunks, history=None):
    """Assemble the chat messages: system prompt, prior turns, then context and question."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append(
        {
            "role": "user",
            "content": f"Context:\n\n{build_context(chunks)}\n\nQuestion: {question}",
        }
    )
    return messages


NO_MATCH = "Nothing in the indexed project content matches that question."


def answer(question, top_n=TOP_N, limit=CHUNK_LIMIT, where=None, pin_work_item=None,
           history=None):
    """Answer a question from the indexed corpus.

    Returns the answer text, the source labels behind it, and the raw chunks.
    """
    chunks = retrieve(
        question, top_n=top_n, limit=limit, where=where, pin_work_item=pin_work_item
    )
    if not chunks:
        return {"answer": NO_MATCH, "sources": [], "chunks": []}

    deployment = chat_deployment()
    response = get_client().chat.completions.create(
        model=deployment, messages=build_messages(question, chunks, history)
    )
    cost_log.log_usage("chat", deployment, getattr(response, "usage", None))

    return {
        "answer": response.choices[0].message.content,
        "sources": [source_label(c["metadata"]) for c in chunks],
        "chunks": chunks,
    }


def answer_stream(question, top_n=TOP_N, limit=CHUNK_LIMIT, where=None,
                  pin_work_item=None, history=None):
    """Answer a question, yielding events as the model produces tokens.

    Events: one `sources` first so the UI can render citations before any text
    arrives, then a `token` per delta, then a single `done`.
    """
    chunks = retrieve(
        question, top_n=top_n, limit=limit, where=where, pin_work_item=pin_work_item
    )

    yield {"type": "sources", "sources": [source_label(c["metadata"]) for c in chunks]}

    if not chunks:
        yield {"type": "token", "text": NO_MATCH}
        yield {"type": "done", "usage": None}
        return

    deployment = chat_deployment()
    stream = get_client().chat.completions.create(
        model=deployment,
        messages=build_messages(question, chunks, history),
        stream=True,
        # Without this the streamed response carries no usage at all and every
        # streamed call would log null token counts.
        stream_options={"include_usage": True},
    )

    usage = None
    for part in stream:
        if getattr(part, "usage", None):
            usage = part.usage
        # The final usage-only chunk has an empty choices list.
        if not part.choices:
            continue
        text = getattr(part.choices[0].delta, "content", None)
        if text:
            yield {"type": "token", "text": text}

    cost_log.log_usage("chat_stream", deployment, usage)
    yield {
        "type": "done",
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
        },
    }
