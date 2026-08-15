"""Chunk the ingested corpus, embed it, and store it in ChromaDB.

    python index_corpus.py            # upsert, safe to re-run
    python index_corpus.py --rebuild  # drop the collection first
"""

import argparse
import json

import chunking
import embeddings
import vector_store
from ingestion import WIKI_PAGES_FILE, WORK_ITEMS_FILE


def load_corpus():
    if not WORK_ITEMS_FILE.exists():
        raise SystemExit(f"{WORK_ITEMS_FILE} not found. Run `python ingestion.py` first.")

    work_items = json.loads(WORK_ITEMS_FILE.read_text())
    wiki_pages = (
        json.loads(WIKI_PAGES_FILE.read_text()) if WIKI_PAGES_FILE.exists() else []
    )
    return work_items, wiki_pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild", action="store_true", help="Delete the collection before indexing."
    )
    args = parser.parse_args()

    if args.rebuild:
        vector_store.reset()
        print("Collection dropped.")

    work_items, wiki_pages = load_corpus()
    chunks = chunking.build_chunks(work_items, wiki_pages)
    print(f"{len(chunks)} chunks from {len(work_items)} work items and {len(wiki_pages)} wiki pages")

    print("Embedding...")
    vectors = embeddings.embed_texts([c["text"] for c in chunks])

    vector_store.upsert_chunks(chunks, vectors)
    print(f"Stored. Collection now holds {vector_store.count()} vectors.")


if __name__ == "__main__":
    main()
