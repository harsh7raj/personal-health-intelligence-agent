"""The app's notion of "now" (memory.md D16).

Call clock.now() instead of datetime.now(...), so the demo replay (Phase 7) can run the
real pipeline "as of" past dates with frozen_at(). Model created_at defaults use it too.

Auth deliberately stays on real time (core/security.py, api/deps.py, doctor-access
expiry), and so does the LLM usage log, which tracks real spend.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

_frozen: datetime | None = None


def _as_utc(when: datetime) -> datetime:
    """Aware UTC datetime; a naive value is taken to already be UTC."""
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def now() -> datetime:
    """Current time as an aware UTC datetime, or the frozen time inside frozen_at()."""
    return _frozen if _frozen is not None else datetime.now(timezone.utc)


@contextmanager
def frozen_at(when: datetime) -> Iterator[datetime]:
    """Pin now() to `when` for the duration of the block (nestable; restores on exit).
    Process-wide: meant for single-threaded scripts like the demo replay, not requests."""
    global _frozen
    previous, _frozen = _frozen, _as_utc(when)
    try:
        yield _frozen
    finally:
        _frozen = previous
