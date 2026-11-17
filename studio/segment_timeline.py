"""Map FFmpeg segment CSV timestamps to the recording's audio-clock timeline.

FFmpeg's CSV values are media timestamps, which may start far from zero for
livestream HLS sources. Each FFmpeg reconnect has its own start timestamp.
Never infer segment positions solely from cumulative durations.
"""
import math
from pathlib import Path


def index_rows(rows, seen, base, origin, folder):
    """Return (new_segments, new_seen, first_timestamp).

    Only consume valid, complete, nonempty files in sequence. A partially
    written CSV row must be retried during the next scan.
    """
    result = []
    offset = seen
    for row in rows[seen:]:
        fields = row.split(",")
        if len(fields) < 3:
            break
        name = fields[0].strip().strip('"')
        try:
            start, end = float(fields[1]), float(fields[2])
        except ValueError:
            break
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            break
        # FFmpeg is the only writer of the CSV, but still refuse paths outside
        # our private segment folder or unexpected filenames.
        if not name.startswith("p") or not name.endswith(".ts") or Path(name).name != name:
            break
        path = folder / name
        if not path.is_file() or path.stat().st_size == 0:
            break
        if origin is None:
            origin = start
        local_start = max(0.0, start - origin)
        local_end = max(local_start, end - origin)
        result.append((path, base + local_start, base + local_end))
        offset += 1
    return result, offset, origin


def latest_video_time(segments):
    """The last indexed, finalized video-segment timestamp."""
    return max((end for _, _, end in segments), default=0.0)


def video_diagnostics(audio_seconds, video_seconds, segments):
    lag = max(0.0, audio_seconds - video_seconds)
    return {"audio_sec": round(audio_seconds, 1), "video_sec": round(video_seconds, 1),
            "video_lag_sec": round(lag, 1), "segments": len(segments),
            "video_ready": bool(segments) and lag <= 25.0}
