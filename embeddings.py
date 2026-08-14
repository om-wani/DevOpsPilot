"""Embed text with text-embedding-3-small (1536 dimensions)."""

import cost_log
from llm_client import embed_deployment, get_client

DIMENSIONS = 1536

# The embeddings endpoint accepts a list; keep batches modest so one failure
# does not cost a whole corpus.
BATCH_SIZE = 64


def embed_texts(texts, feature="embeddings"):
    """Embed a list of texts, preserving order."""
    if not texts:
        return []

    client = get_client()
    deployment = embed_deployment()

    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        response = client.embeddings.create(model=deployment, input=batch)
        cost_log.log_usage(feature, deployment, getattr(response, "usage", None))
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))

    return vectors


def embed_query(text):
    """Embed a single question. Same model as the corpus, by design."""
    return embed_texts([text], feature="query_embedding")[0]
