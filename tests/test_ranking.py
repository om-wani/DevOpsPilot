import pytest

import rag


def result(chunk_id, distance, source_type="work_item", source_id="1", title=""):
    return {
        "id": chunk_id,
        "text": f"text for {chunk_id}",
        "distance": distance,
        "metadata": {"source_type": source_type, "source_id": source_id, "title": title},
    }


def test_empty_results_return_empty_list():
    assert rag.select_chunks([]) == []


def test_closest_chunk_comes_first():
    selected = rag.select_chunks([result("b", 0.7), result("a", 0.1)], limit=5)
    assert [c["id"] for c in selected] == ["a", "b"]


def test_ties_break_on_chunk_id_for_determinism():
    results = [result("z", 0.4), result("a", 0.4), result("m", 0.4)]
    assert [c["id"] for c in rag.select_chunks(results, limit=3)] == ["a", "m", "z"]


def test_chunk_limit_is_enforced():
    results = [result(str(n), n / 10) for n in range(20)]
    assert len(rag.select_chunks(results, limit=5)) == 5


def test_limit_larger_than_result_count_returns_everything():
    results = [result("a", 0.1), result("b", 0.2)]
    assert len(rag.select_chunks(results, limit=50)) == 2


def test_zero_limit_returns_nothing():
    assert rag.select_chunks([result("a", 0.1)], limit=0) == []


def test_negative_limit_rejected():
    with pytest.raises(ValueError):
        rag.select_chunks([result("a", 0.1)], limit=-1)


def test_missing_distance_does_not_crash_ranking():
    results = [{"id": "a", "text": "t", "metadata": {}}, result("b", 0.9)]
    assert [c["id"] for c in rag.select_chunks(results, limit=2)] == ["a", "b"]


def test_work_item_source_label():
    assert rag.source_label({"source_type": "work_item", "source_id": "12"}) == "work item 12"


def test_wiki_source_label_uses_title():
    label = rag.source_label({"source_type": "wiki", "source_id": "4", "title": "Setup Guide"})
    assert label == "wiki: Setup Guide"


def test_context_tags_every_chunk_with_its_source():
    chunks = [
        result("a", 0.1),
        result("b", 0.2, source_type="wiki", source_id="4", title="Setup Guide"),
    ]
    context = rag.build_context(chunks)
    assert "[work item 1]" in context
    assert "[wiki: Setup Guide]" in context
