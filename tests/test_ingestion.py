import ingestion


def test_strip_html_flattens_tags_and_entities():
    html = "<div>First line<br/>Second &amp; third</div>"
    assert ingestion.strip_html(html) == "First line\nSecond & third"


def test_strip_html_leaves_plain_text_alone():
    assert ingestion.strip_html("Just a sentence.") == "Just a sentence."


def test_strip_html_handles_none_and_empty():
    assert ingestion.strip_html(None) == ""
    assert ingestion.strip_html("") == ""


def test_dedupe_keeps_lowest_id_per_distinct_content():
    pages = [
        {"id": 10, "path": "/API Conventions", "content_hash": "aaa"},
        {"id": 5, "path": "/API-Conventions", "content_hash": "aaa"},
        {"id": 7, "path": "/Architecture", "content_hash": "bbb"},
    ]

    kept = ingestion._dedupe_by_hash(pages)

    assert [p["id"] for p in kept] == [5, 7]


def test_dedupe_on_empty_input():
    assert ingestion._dedupe_by_hash([]) == []
