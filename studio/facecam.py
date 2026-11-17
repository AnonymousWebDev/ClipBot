"""Validated normalized crop boxes and FFmpeg filter for stacked facecam shorts."""
import math

TOP_HEIGHT = 520


def validate_box(box, *, optional=False):
    """Keep crop regions inside the source frame; 0..1 coordinates survive resolution changes."""
    if optional and (box is None or box == {}):
        return None
    if not isinstance(box, dict) or set(box) != {"x", "y", "w", "h"}:
        raise ValueError("Draw a rectangle around the facecam first.")
    values = {}
    for key in ("x", "y", "w", "h"):
        v = box[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError("Crop coordinates must be finite numbers.")
        values[key] = float(v)
    x, y, w, h = (values[k] for k in ("x", "y", "w", "h"))
    if x < 0 or y < 0 or w < 0.03 or h < 0.03 or x + w > 1.000001 or y + h > 1.000001:
        raise ValueError("The selected rectangle must be inside the frame and at least 3% wide and tall.")
    return {k: round(v, 6) for k, v in values.items()}


def pixel_crop(box, source_width, source_height):
    """Source-aligned integer crop; FFmpeg handles odd dimensions with scaling."""
    if not source_width or not source_height:
        raise ValueError("Video dimensions must be available for facecam cropping.")
    x = max(0, min(source_width - 2, round(box["x"] * source_width)))
    y = max(0, min(source_height - 2, round(box["y"] * source_height)))
    w = max(2, min(source_width - x, round(box["w"] * source_width)))
    h = max(2, min(source_height - y, round(box["h"] * source_height)))
    return x, y, w, h


def stacked_filter(source_width, source_height, facecam_box, gameplay_box=None, *, out_width=1080, out_height=1920, fps=30):
    """Full facecam at top and full selected gameplay inside the lower panel.

    Uses blurred background rather than cropping half the gameplay horizontally.
    Source and crop dimensions only come from validated server-side layout presets.
    """
    face = validate_box(facecam_box)
    game = validate_box(gameplay_box, optional=True)
    face_x, face_y, face_w, face_h = pixel_crop(face, source_width, source_height)
    if game is None:
        game_x, game_y, game_w, game_h = 0, 0, source_width, source_height
    else:
        game_x, game_y, game_w, game_h = pixel_crop(game, source_width, source_height)
    top = round(out_height * TOP_HEIGHT / 1920)
    bottom = out_height - top
    # Draw over a softened copy of the whole source. Keep each selected region in full.
    return (
        f"[0:v]fps={fps},split=3[back][web][game];"
        f"[back]scale={out_width}:{out_height}:force_original_aspect_ratio=increase,"
        f"crop={out_width}:{out_height},boxblur=16:2,eq=brightness=-0.25[bg];"
        f"[web]crop={face_w}:{face_h}:{face_x}:{face_y},"
        f"scale={out_width}:{top}:force_original_aspect_ratio=decrease,setsar=1[face];"
        f"[bg][face]overlay=(W-w)/2:({top}-h)/2:shortest=1[top];"
        f"[game]crop={game_w}:{game_h}:{game_x}:{game_y},"
        f"scale={out_width}:{bottom}:force_original_aspect_ratio=decrease,setsar=1[play];"
        f"[top][play]overlay=(W-w)/2:{top}+({bottom}-h)/2:shortest=1,setsar=1[v0];"
    )
