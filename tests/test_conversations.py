import pytest

import conversations


@pytest.fixture(autouse=True)
def clear():
    conversations.reset()
    yield
    conversations.reset()


def test_unknown_conversation_has_no_history():
    assert conversations.get("never-seen") == []


def test_exchange_is_recorded_as_two_turns():
    conversations.append("c1", "first question", "first answer")
    assert conversations.get("c1") == [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
    ]


def test_turns_accumulate_across_exchanges():
    conversations.append("c1", "q1", "a1")
    conversations.append("c1", "q2", "a2")
    assert len(conversations.get("c1")) == 4


def test_oldest_turns_fall_off_past_the_cap():
    for n in range(20):
        conversations.append("c1", f"q{n}", f"a{n}")

    turns = conversations.get("c1")
    assert len(turns) == conversations.MAX_TURNS
    assert turns[-1]["content"] == "a19"
    assert all("q0" != t["content"] for t in turns)


def test_conversations_are_isolated():
    conversations.append("c1", "q", "a")
    assert conversations.get("c2") == []


def test_no_conversation_id_means_no_storage():
    assert conversations.append(None, "q", "a") == []
    assert conversations.get(None) == []


def test_expired_conversation_is_forgotten(monkeypatch):
    conversations.append("c1", "q", "a")
    monkeypatch.setattr(conversations, "TTL_SECONDS", -1)
    assert conversations.get("c1") == []


def test_returned_history_is_a_copy():
    conversations.append("c1", "q", "a")
    conversations.get("c1").append({"role": "user", "content": "injected"})
    assert len(conversations.get("c1")) == 2
