"""Small, dependency-free helpers for a time-based rolling video buffer."""


def prune(segments, keep_from, pinned):
    """Delete expired segments except ones needed by queued live clips.

    Each pinned interval is (start, end) in stream seconds. Expiry only
    happens once the segment is outside the current rolling window *and* all
    pending clip ranges. A pinned old segment must not retain unrelated files.
    """
    retained = []
    ranges = tuple(pinned.values())
    for segment in segments:
        path, start, end = segment
        protected = any(end > lo and start < hi for lo, hi in ranges)
        if end < keep_from and not protected:
            path.unlink(missing_ok=True)
        else:
            retained.append(segment)
    return retained
