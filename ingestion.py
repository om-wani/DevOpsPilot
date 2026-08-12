"""Pull work items and wiki pages from Azure DevOps into local JSON.

Everything downstream (chunking, embedding, retrieval) reads these files, so
run this first and re-run it whenever the board changes.

    python ingestion.py
"""

import argparse
import hashlib
import json
import re
from html import unescape
from pathlib import Path

import devops_client as dc

DATA_DIR = Path(__file__).parent / "data"
WORK_ITEMS_FILE = DATA_DIR / "work_items.json"
WIKI_PAGES_FILE = DATA_DIR / "wiki_pages.json"

_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"[ \t]*\n[ \t]*")


def strip_html(text):
    """Flatten the HTML the work item API returns into plain text."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", text, flags=re.I)
    text = _TAG.sub("", text)
    return _WHITESPACE.sub("\n", unescape(text)).strip()


def fetch_work_items():
    """Every work item in the project with its comments, ascending by id."""
    ids = dc.list_work_item_ids()
    raw = dc.get_work_items(ids)

    items = []
    for item in raw:
        fields = item.get("fields", {})
        item_id = item.get("id")
        items.append(
            {
                "id": item_id,
                "type": fields.get("System.WorkItemType", ""),
                "state": fields.get("System.State", ""),
                "title": fields.get("System.Title", ""),
                "description": strip_html(fields.get("System.Description")),
                "comments": [strip_html(c) for c in dc.get_comments(item_id)],
                "changed_date": fields.get("System.ChangedDate", ""),
            }
        )

    items.sort(key=lambda i: i["id"])
    return items


def fetch_wiki_pages():
    """Every wiki page with its markdown, deduplicated by content.

    The test wiki holds each page twice, once under a dashed path and once
    under a spaced one, because the seed script ran more than once. Indexing
    both would return the same page twice for every query, so keep the copy
    with the lowest page id and drop the rest.
    """
    wiki = dc.get_wiki_name()

    pages = []
    for path in dc.list_wiki_page_paths(wiki):
        page = dc.get_wiki_page(wiki, path)
        content = page.get("content") or ""
        if not content.strip():
            continue
        pages.append(
            {
                "id": page.get("id"),
                "path": path,
                "title": path.lstrip("/").replace("-", " "),
                "content": content,
                "content_hash": hashlib.sha1(content.encode()).hexdigest(),
            }
        )

    return _dedupe_by_hash(pages)


def _dedupe_by_hash(pages):
    """Keep one page per distinct content, preferring the lowest page id."""
    best = {}
    for page in sorted(pages, key=lambda p: (p["id"] is None, p["id"])):
        best.setdefault(page["content_hash"], page)
    return sorted(best.values(), key=lambda p: p["id"])


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-wiki", action="store_true", help="Pull work items only."
    )
    args = parser.parse_args()

    print("Fetching work items...")
    items = fetch_work_items()
    write_json(WORK_ITEMS_FILE, items)
    comment_count = sum(len(i["comments"]) for i in items)
    print(f"  {len(items)} work items, {comment_count} comments -> {WORK_ITEMS_FILE}")

    if args.skip_wiki:
        return

    print("Fetching wiki pages...")
    pages = fetch_wiki_pages()
    write_json(WIKI_PAGES_FILE, pages)
    print(f"  {len(pages)} pages -> {WIKI_PAGES_FILE}")


if __name__ == "__main__":
    main()
