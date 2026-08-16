"""Ask a question about the Azure DevOps project from the command line.

    python main.py "What is blocking the auth work?"

Run `python ingestion.py` and `python index_corpus.py` first.
"""

import argparse
import sys

import rag
import vector_store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="*", help="The question to ask.")
    parser.add_argument("--top-n", type=int, default=rag.TOP_N, help="Chunks to retrieve.")
    parser.add_argument(
        "--limit", type=int, default=rag.CHUNK_LIMIT, help="Chunks to put in the prompt."
    )
    args = parser.parse_args()

    if vector_store.count() == 0:
        raise SystemExit("Vector store is empty. Run `python index_corpus.py` first.")

    question = " ".join(args.question).strip() or input("Question: ").strip()
    if not question:
        raise SystemExit("No question given.")

    result = rag.answer(question, top_n=args.top_n, limit=args.limit)

    print(result["answer"])
    if result["sources"]:
        print("\nSources:")
        for source in dict.fromkeys(result["sources"]):
            print(f"  - {source}")


if __name__ == "__main__":
    sys.exit(main())
