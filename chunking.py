"""Turn ingested work items and wiki pages into embeddable chunks.

Pure functions, no I/O and no network, so the boundary rules are testable on
their own.

A chunk is a dict: id, text, and metadata. Chunk ids are deterministic
(`{source_type}:{source_id}:{n}`) so re-embedding overwrites the old vector
instead of adding a second copy alongside it.
"""

MAX_WORDS = 500
OVERLAP_WORDS = 50


def chunk_work_item(item):
    """One chunk per work item. Title, description and comments read as a unit."""
    parts = [f"Work item {item['id']}: {item['title']}"]
    if item.get("state") or item.get("type"):
        parts.append(f"Type: {item.get('type', '')}. State: {item.get('state', '')}.")
    if item.get("description"):
        parts.append(item["description"])
    for comment in item.get("comments") or []:
        parts.append(f"Comment: {comment}")

    return [
        {
            "id": f"work_item:{item['id']}:0",
            "text": "\n\n".join(parts),
            "metadata": {
                "source_type": "work_item",
                "source_id": str(item["id"]),
                "title": item["title"],
                "state": item.get("state", ""),
                "type": item.get("type", ""),
            },
        }
    ]


def chunk_wiki_page(page, max_words=MAX_WORDS, overlap_words=OVERLAP_WORDS):
    """Split a wiki page once it runs past `max_words`, with overlap between parts."""
    header = f"Wiki page: {page['title']}"
    pieces = split_words(page["content"], max_words, overlap_words)

    chunks = []
    for n, piece in enumerate(pieces):
        chunks.append(
            {
                "id": f"wiki:{page['id']}:{n}",
                "text": f"{header}\n\n{piece}",
                "metadata": {
                    "source_type": "wiki",
                    "source_id": str(page["id"]),
                    "title": page["title"],
                    "path": page.get("path", ""),
                    "part": n,
                },
            }
        )
    return chunks


def split_words(text, max_words=MAX_WORDS, overlap_words=OVERLAP_WORDS):
    """Split text into word windows of `max_words` that overlap by `overlap_words`.

    Text at or under the limit comes back as a single piece.
    """
    if max_words <= 0:
        raise ValueError("max_words must be positive")
    if not 0 <= overlap_words < max_words:
        raise ValueError("overlap_words must be non-negative and below max_words")

    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [text.strip()]

    step = max_words - overlap_words
    pieces = []
    for start in range(0, len(words), step):
        window = words[start : start + max_words]
        if not window:
            break
        pieces.append(" ".join(window))
        if start + max_words >= len(words):
            break
    return pieces


def build_chunks(work_items, wiki_pages):
    """All chunks for a full corpus, work items first."""
    chunks = []
    for item in work_items:
        chunks.extend(chunk_work_item(item))
    for page in wiki_pages:
        chunks.extend(chunk_wiki_page(page))
    return chunks
