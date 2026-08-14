"""Append token usage for every model call to a local JSONL file.

Phase 4 builds a dashboard on top of this. Until then the file is the record.
Prompt and completion tokens stay separate so prompt cost is trackable on its own.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path(__file__).parent / "data" / "usage.jsonl"


def log_usage(feature, deployment, usage):
    """Record one call. `usage` is the response's usage object, or None."""
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "feature": feature,
        "deployment": deployment,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")

    return entry
