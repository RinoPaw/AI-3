"""Startup timing helpers for diagnosing slow application launches."""

from time import perf_counter


_started = perf_counter()
_last = _started


def boot_log(stage: str) -> None:
    """Print elapsed time since the previous and first startup checkpoint."""
    global _last

    now = perf_counter()
    print(
        f"[BOOT] {stage}: +{now - _last:.3f}s "
        f"(total {now - _started:.3f}s)",
        flush=True,
    )
    _last = now
