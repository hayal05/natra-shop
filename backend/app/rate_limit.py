"""
NATRA backend — simple in-memory rate limiter.

Phase 4, Task 44: brute-force protection for POST /sellers/login and
POST /admin/login.

Deliberately in-memory and per-process, not backed by Redis or any
other external store — this matches the project's current deployment
target (Task 46: a single Uvicorn process behind Nginx on Oracle Cloud
Free Tier), where there's exactly one process to hold counters in.
Counters reset on every restart/deploy, which is an accepted trade-off
for a brute-force *slowdown*, not a security boundary that needs to
survive restarts. If a future task scales this to multiple Uvicorn
worker processes, per-process counters would let an attacker get
roughly N attempts per worker instead of N total — at that point this
needs to move to a shared store (e.g. Redis); flagging that now so it
isn't a silent surprise later.
"""

import time
from collections import defaultdict
from threading import Lock

# 5 attempts per rolling 60 seconds, per key. Deliberately not
# configurable via environment variable for this task — a fixed,
# reasonable default is enough to slow down credential-stuffing/brute-
# force attempts without adding another env var to document/tune; can
# become configurable later if a concrete need arises.
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 60.0

_attempts: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


class RateLimitExceeded(Exception):
    """
    Raised when `key` has already made `_MAX_ATTEMPTS` attempts within
    the trailing `_WINDOW_SECONDS`. `retry_after` is the number of whole
    seconds until the oldest attempt in the current window ages out and
    a new attempt would be allowed again — suitable for a `Retry-After`
    response header.
    """

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s")


def check_rate_limit(key: str) -> None:
    """
    Records one attempt for `key` (e.g. "seller_login:203.0.113.7") and
    raises `RateLimitExceeded` if that pushes `key` over `_MAX_ATTEMPTS`
    attempts within the trailing `_WINDOW_SECONDS`.

    A sliding window, not a fixed calendar-aligned one: on every call,
    timestamps older than `_WINDOW_SECONDS` are pruned from `key`'s
    history first, so the limit is always "at most N attempts in the
    last `_WINDOW_SECONDS`", not "N per clock-aligned minute" (which
    would let a caller burst 2N attempts across a minute boundary).

    A rejected (rate-limited) attempt is NOT itself recorded as a new
    attempt — it doesn't extend the window further, so once the oldest
    attempt in the window ages out, the caller is immediately allowed
    one more try rather than being pushed back every time they retry
    too early.

    `time.monotonic()` is used rather than wall-clock time so this is
    unaffected by system clock adjustments (NTP sync, manual changes).
    Process-wide, thread-safe via a single `Lock` — call volume on two
    low-traffic login endpoints doesn't need anything more elaborate
    (e.g. per-key locks or a lock-free structure).
    """
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    with _lock:
        timestamps = _attempts[key]
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        if len(timestamps) >= _MAX_ATTEMPTS:
            retry_after = int(_WINDOW_SECONDS - (now - timestamps[0])) + 1
            raise RateLimitExceeded(retry_after=retry_after)

        timestamps.append(now)
