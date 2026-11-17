"""Map FFmpeg segment CSV timestamps to the recording's audio-clock timeline.

FFmpeg's CSV values are media timestamps, which may start far from zero for
livestream HLS sources. Each FFmpeg reconnect has its own start timestamp.
Never infer segment positions solely from cumulative durations.
"""
import math
from pathlib import Path


# The 720p Twitch recorder normally writes ~6s files. A media timestamp
# discontinuity can turn one file into a multi-minute monster. Never mistake
# its CSV duration for usable clip footage.
NOMINAL_SEGMENT_SEC = 6.0
MAX_SEGMENT_SEC = 18.0
MAX_SEGMENT_BYTES = 40 * 1024 * 1024


def index_rows(rows, seen, base, origin, folder):
    """Return (new_segments, new_seen, first_timestamp).

    CSV timestamps are usually consecutive, but Twitch HLS can jump abruptly
    backwards or forwards mid-recording. Rebuild a local monotonic timeline
    from each completed file's *bounded* duration. An anomalous file consumes
    one nominal segment of timeline but is excluded, leaving an honest gap in
    the available footage. Earlier rows are replayed without checking pruned
    files, so reconnects and rolling-buffer pruning remain safe.

    Only consume an incomplete final CSV row when its TS file is fully written.
    """
    result = []
    offset = seen
    previous_raw_end = None
    local_end = 0.0
    first = origin
    for idx, row in enumerate(rows):
        fields = row.split(",")
        if len(fields) < 3:
            break
        name = fields[0].strip().strip('"')
        try:
            start, end = float(fields[1]), float(fields[2])
        except ValueError:
            break
        if not math.isfinite(start) or not math.isfinite(end):
            break
        # FFmpeg is the only writer of the CSV, but still refuse unsafe paths.
        if not name.startswith("p") or not name.endswith(".ts") or Path(name).name != name:
            break
        path = folder / name
        size = None
        if idx >= seen:
            try:
                size = path.stat().st_size
            except OSError:
                break
            if size == 0:
                break
        if first is None:
            first = start
        if idx == 0:
            local_start = 0.0
        elif previous_raw_end is None:
            local_start = local_end
        else:
            gap = start - previous_raw_end
            if -2.0 <= gap <= MAX_SEGMENT_SEC:
                # Preserve normal CSV jitter and small genuine media gaps.
                local_start = max(0.0, local_end + gap)
            elif gap > MAX_SEGMENT_SEC:
                # An unexpected forward jump is missing footage, not hours
                # of video. Represent a bounded gap for clip-safety.
                local_start = local_end + NOMINAL_SEGMENT_SEC
            else:
                # A backwards PTS jump is a new timestamp epoch.
                local_start = local_end
        duration = end - start
        if not (0.0 < duration <= MAX_SEGMENT_SEC) or (
            size is not None and size > MAX_SEGMENT_BYTES
        ):
            # Drop an impossible/overgrown segment; keep the gap. Do not allow
            # one 8920-second timestamp to poison the whole recording clock.
            local_end = local_start + NOMINAL_SEGMENT_SEC
            previous_raw_end = None
        else:
            local_end = local_start + duration
            previous_raw_end = end
            if idx >= seen:
                result.append((path, base + local_start, base + local_end))
        if idx >= seen:
            offset = idx + 1
    return result, offset, first


def latest_video_time(segments):
    """The last indexed, finalized video-segment timestamp."""
    return max((end for _, _, end in segments), default=0.0)


def video_diagnostics(audio_seconds, video_seconds, segments):
    lag = max(0.0, audio_seconds - video_seconds)
    return {"audio_sec": round(audio_seconds, 1), "video_sec": round(video_seconds, 1),
            "video_lag_sec": round(lag, 1), "segments": len(segments),
            "video_ready": bool(segments) and lag <= 25.0}


def continuous_tail(segments, *, gap_tolerance=2.0):
    """Earliest start and latest end of the newest continuous saved video run.

    A stale segment from a previous reconnect must not make it look like 30s
    of recent footage is ready when only one 6s piece exists.
    """
    valid = sorted(((start, end) for path, start, end in segments
                    if end > start and path.is_file()), key=lambda p: (p[1], p[0]))
    if not valid:
        return (0.0, 0.0)
    start, end = valid[-1]
    for earlier_start, earlier_end in reversed(valid[:-1]):
        if earlier_end < start - gap_tolerance:
            break
        start = min(start, earlier_start)
    return start, end


def video_stalled(audio_now, last_video_progress_audio, process_age, *, stall_sec=25, warmup_sec=35):
    """True when audio is advancing but the TS recorder has stopped writing.

    A single live stream may need up to several GOPs to start producing TS;
    require both a warm-up and a sustained period with no new TS bytes.
    This detects a frozen *video output*, not a disconnected audio process.
    """
    return (process_age >= warmup_sec
            and audio_now - last_video_progress_audio >= stall_sec)


def segment_bytes_snapshot(folder, prefix):
    """(filename, size) of newest nonempty TS file; no stream URLs are read."""
    files = sorted(folder.glob(prefix + "_*.ts"))
    for path in reversed(files):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > 0:
            return (path.name, size)
    return None
