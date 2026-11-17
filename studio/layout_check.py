"""Cheap, fail-closed facecam checks for chat-generated livestream highlights.

Uses 3 JPEG samples decoded from the retained raw clip and OpenCV's bundled
frontal-face cascade. A failed/missing detector never means a clip is approved.
This is a conservative first-pass safety gate, not identity verification.
"""
import math
import subprocess
from pathlib import Path

from . import facecam


def summarize(hits):
    """A clip is verified only if 2 of 3 readable samples contain a face."""
    count = sum(v is True for v in hits)
    valid = sum(v is not None for v in hits)
    if valid < 3:
        return {"status": "review", "reason": "Could not inspect every sampled frame.",
                "faces_found": count, "samples": valid}
    if count < 2:
        return {"status": "review", "reason": "Saved webcam position may have moved or be empty.",
                "faces_found": count, "samples": valid}
    return {"status": "verified", "reason": "Face found in the saved webcam region.",
            "faces_found": count, "samples": valid}


def _review(reason):
    return {"status": "review", "reason": reason, "faces_found": 0, "samples": 0}


def inspect(src: Path, start: float, end: float, box: dict, *, layout: str, source_width: int, source_height: int):
    """Inspect a retained raw clip. start/end are seconds relative to *src*.

    FFmpeg seeks three positions, outputs small JPEG frames in memory, and does
    not encode any video. The webcam crop is a saved, normalized region.
    """
    if layout != "facecam_top":
        return _review("Choose the facecam-above-gameplay layout in the Layout Editor.")
    if not box:
        return _review("No webcam region selected. Open the Layout Editor.")
    try:
        face = facecam.validate_box(box)
    except ValueError:
        return _review("Saved webcam region is invalid. Re-select it in the Layout Editor.")
    if not all(math.isfinite(v) for v in (start, end)) or end - start < 3:
        return _review("Clip time range is too short to inspect.")
    if not source_width or not source_height:
        return _review("Source video dimensions are unavailable.")
    try:
        import cv2
        import numpy as np
        cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
        if cascade.empty():
            return _review("Local face detector is unavailable. Review this clip manually.")
        cv2.setNumThreads(1)
    except (ImportError, AttributeError, OSError):
        return _review("OpenCV face detector is not installed. Review this clip manually.")

    duration = end - start
    hits = []
    for fraction in (0.2, 0.5, 0.8):
        position = max(0.0, start + duration * fraction)
        try:
            p = subprocess.run(
                ["ffmpeg", "-nostdin", "-threads", "1", "-v", "error", "-ss", f"{position:.3f}",
                 "-i", str(src), "-frames:v", "1", "-vf", "scale=640:-2:flags=fast_bilinear",
                 "-q:v", "5", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
                capture_output=True, timeout=12,
            )
            if p.returncode or not p.stdout:
                hits.append(None)
                continue
            image = cv2.imdecode(np.frombuffer(p.stdout, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if image is None:
                hits.append(None)
                continue
            height, width = image.shape[:2]
            x, y, w, h = facecam.pixel_crop(face, width, height)
            region = image[y:y+h, x:x+w]
            if region.size < 25 * 25 or min(region.shape) < 30:
                hits.append(False)
                continue
            # Restrict detection to the selected webcam region, never gameplay.
            detected = cascade.detectMultiScale(region, scaleFactor=1.1, minNeighbors=4,
                                                 minSize=(22, 22))
            hits.append(len(detected) > 0)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            hits.append(None)
    result = summarize(hits)
    result["method"] = "opencv-haar-3frame"
    return result
