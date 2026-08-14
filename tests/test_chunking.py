import chunking


def test_work_item_becomes_one_chunk_with_metadata():
    item = {
        "id": 7,
        "type": "Issue",
        "state": "Doing",
        "title": "Fix retrieval",
        "description": "Body text.",
        "comments": ["First note", "Second note"],
    }

    chunks = chunking.chunk_work_item(item)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["id"] == "work_item:7:0"
    assert chunk["metadata"] == {
        "source_type": "work_item",
        "source_id": "7",
        "title": "Fix retrieval",
        "state": "Doing",
        "type": "Issue",
    }
    assert "Fix retrieval" in chunk["text"]
    assert "First note" in chunk["text"]
    assert "Second note" in chunk["text"]


def test_work_item_without_description_or_comments():
    chunks = chunking.chunk_work_item(
        {"id": 1, "type": "Task", "state": "To Do", "title": "Bare", "comments": []}
    )
    assert len(chunks) == 1
    assert "Bare" in chunks[0]["text"]


def test_short_text_is_one_piece():
    assert chunking.split_words("one two three", max_words=500) == ["one two three"]


def test_empty_text_yields_nothing():
    assert chunking.split_words("   ") == []


def test_text_at_the_limit_is_not_split():
    text = " ".join(str(n) for n in range(10))
    assert len(chunking.split_words(text, max_words=10, overlap_words=2)) == 1


def test_text_one_word_over_the_limit_is_split():
    text = " ".join(str(n) for n in range(11))
    pieces = chunking.split_words(text, max_words=10, overlap_words=2)
    assert len(pieces) == 2


def test_pieces_overlap_by_the_requested_word_count():
    text = " ".join(str(n) for n in range(30))
    pieces = chunking.split_words(text, max_words=10, overlap_words=3)

    first_tail = pieces[0].split()[-3:]
    second_head = pieces[1].split()[:3]
    assert first_tail == second_head


def test_split_covers_every_word():
    text = " ".join(str(n) for n in range(53))
    pieces = chunking.split_words(text, max_words=10, overlap_words=2)
    seen = {word for piece in pieces for word in piece.split()}
    assert seen == {str(n) for n in range(53)}


def test_zero_overlap_is_allowed():
    text = " ".join(str(n) for n in range(20))
    pieces = chunking.split_words(text, max_words=10, overlap_words=0)
    assert len(pieces) == 2
    assert pieces[0].split()[-1] == "9"
    assert pieces[1].split()[0] == "10"


def test_invalid_overlap_rejected():
    import pytest

    with pytest.raises(ValueError):
        chunking.split_words("a b c", max_words=5, overlap_words=5)
    with pytest.raises(ValueError):
        chunking.split_words("a b c", max_words=0)


def test_long_wiki_page_splits_into_numbered_chunks():
    page = {"id": 4, "title": "Setup Guide", "path": "/Setup-Guide", "content": " ".join(["word"] * 1200)}

    chunks = chunking.chunk_wiki_page(page)

    assert len(chunks) > 1
    assert [c["id"] for c in chunks] == [f"wiki:4:{n}" for n in range(len(chunks))]
    assert all(c["metadata"]["source_type"] == "wiki" for c in chunks)
    assert [c["metadata"]["part"] for c in chunks] == list(range(len(chunks)))
    assert all(c["text"].startswith("Wiki page: Setup Guide") for c in chunks)


def test_chunk_ids_are_stable_across_runs():
    item = {"id": 3, "type": "Task", "state": "Done", "title": "T", "comments": []}
    assert chunking.chunk_work_item(item)[0]["id"] == chunking.chunk_work_item(item)[0]["id"]


def test_build_chunks_keeps_ids_unique():
    items = [
        {"id": n, "type": "Task", "state": "To Do", "title": f"T{n}", "comments": []}
        for n in range(5)
    ]
    pages = [
        {"id": n, "title": f"P{n}", "path": f"/P{n}", "content": " ".join(["word"] * 900)}
        for n in range(3)
    ]

    chunks = chunking.build_chunks(items, pages)
    ids = [c["id"] for c in chunks]
    assert len(set(ids)) == len(ids)
