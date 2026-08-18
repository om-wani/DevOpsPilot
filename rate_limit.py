"""Per-user request limiting for the chat endpoint.

A frontend retry loop against a streaming endpoint can run up real Azure OpenAI
cost in seconds, so the limit is on the server, not the client.

In-memory sliding window. This holds for a single process only; once the backend
runs more than one container this has to move to shared storage or the effective
limit becomes the limit times the container count.
"""

import time
from collections import defaultdict, deque

MAX_REQUESTS = 20
WINDOW_SECONDS = 60

_hits = defaultdict(deque)


class RateLimited(Exception):
    """The caller has used up their allowance for the current window."""

    def __init__(self, retry_after):
        super().__init__("Too many requests.")
        self.retry_after = retry_after
        self.message = f"Too many requests. Try again in {retry_after} seconds."


def check(user_id, max_requests=MAX_REQUESTS, window=WINDOW_SECONDS, now=None):
    """Record a request for `user_id`, or raise RateLimited."""
    now = time.monotonic() if now is None else now
    hits = _hits[user_id]

    cutoff = now - window
    while hits and hits[0] <= cutoff:
        hits.popleft()

    if len(hits) >= max_requests:
        retry_after = max(1, int(hits[0] + window - now) + 1)
        raise RateLimited(retry_after)

    hits.append(now)
    return max_requests - len(hits)


def reset():
    """Clear every window. Used by tests."""
    _hits.clear()
