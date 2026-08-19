"""Conversation turns held between requests so follow-up questions keep context.

In-memory and per-process: restarting the server forgets every conversation.
Acceptable while this runs as a single local container; Phase 4 moves it to
real storage alongside the cost table.
"""

import time

MAX_TURNS = 12
TTL_SECONDS = 3600

_store = {}


def _evict_expired(now):
    for key, (_, touched) in list(_store.items()):
        if touched + TTL_SECONDS < now:
            _store.pop(key, None)


def get(conversation_id):
    """Prior turns for a conversation, oldest first."""
    if not conversation_id:
        return []
    entry = _store.get(conversation_id)
    if not entry:
        return []
    turns, touched = entry
    if touched + TTL_SECONDS < time.monotonic():
        _store.pop(conversation_id, None)
        return []
    return list(turns)


def append(conversation_id, question, answer_text):
    """Record one exchange, trimming the oldest turns past the cap."""
    if not conversation_id:
        return []

    now = time.monotonic()
    _evict_expired(now)

    turns = get(conversation_id)
    turns.append({"role": "user", "content": question})
    turns.append({"role": "assistant", "content": answer_text})
    turns = turns[-MAX_TURNS:]

    _store[conversation_id] = (turns, now)
    return turns


def reset():
    """Drop every conversation. Used by tests."""
    _store.clear()
