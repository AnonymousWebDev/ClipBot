"""Facecam crop validation and real FFmpeg filter regression tests."""
import shutil
import subprocess
import unittest

from studio.facecam import pixel_crop, stacked_filter, validate_box


class FacecamTests(unittest.TestCase):
    def setUp(self):
        self.facecam = {"x": .73, "y": .1, "w": .23, "h": .35}

    def test_valid_box_and_optional_gameplay(self):
        self.assertEqual(validate_box(self.facecam), self.facecam)
        self.assertIsNone(validate_box(None, optional=True))
        self.assertIsNone(validate_box({}, optional=True))
        self.assertEqual(pixel_crop(self.facecam, 1920, 1080), (1402, 108, 442, 378))

    def test_reject_unsafe_boxes(self):
        for bad in (
            None,
            {"x": .9, "y": .1, "w": .3, "h": .2},
            {"x": 0, "y": 0, "w": 0, "h": 1},
            {"x": -0.1, "y": 0, "w": .5, "h": .5},
            {"x": float("nan"), "y": 0, "w": .5, "h": .5},
            {"x": True, "y": 0, "w": .5, "h": .5},
            {"x": "0.5", "y": 0, "w": .2, "h": .5},
        ):
            with self.subTest(box=bad), self.assertRaises(ValueError):
                validate_box(bad)

    def test_filter_uses_boxes_without_source_scale_assumptions(self):
        f = stacked_filter(1920, 1080, self.facecam, {
            "x": 0, "y": 0, "w": .68, "h": 1
        })
        self.assertIn("crop=442:378:1402:108", f)
        self.assertIn("crop=1306:1080:0:0", f)
        self.assertTrue(f.endswith("[v0];"))

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_ffmpeg_renders_stacked_frame(self):
        f = stacked_filter(640, 360, self.facecam, out_width=360, out_height=640)
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-f", "lavfi",
             "-i", "testsrc2=size=640x360:rate=15", "-t", "1",
             "-filter_complex", f, "-map", "[v0]", "-frames:v", "1",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=30
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-1500:])


if __name__ == "__main__":
    unittest.main()
