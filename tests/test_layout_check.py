"""Validation-gate regression tests. No Twitch stream or AI service required."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from studio.layout_check import inspect, summarize


class LayoutCheckTests(unittest.TestCase):
    FACE = {"x": 0.7, "y": 0.05, "w": 0.25, "h": 0.35}

    def test_pass_requires_two_of_three_readable_samples(self):
        self.assertEqual(summarize([True, True, False])["status"], "verified")
        self.assertEqual(summarize([True, True, True])["status"], "verified")

    def test_missing_frame_always_requires_review(self):
        self.assertEqual(summarize([True, True, None])["status"], "review")
        self.assertEqual(summarize([False, False, False])["status"], "review")

    def test_missing_selection_fails_closed(self):
        result = inspect(Path("/not-a-video.mp4"), 0, 10, None, layout="facecam_top",
                         source_width=1920, source_height=1080)
        self.assertEqual(result["status"], "review")
        self.assertIn("No webcam", result["reason"])

    def test_wrong_layout_fails_closed(self):
        result = inspect(Path("/not-a-video.mp4"), 0, 10, self.FACE, layout="blur",
                         source_width=1920, source_height=1080)
        self.assertEqual(result["status"], "review")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg unavailable")
    def test_black_video_does_not_get_approved(self):
        try:
            import cv2
            self.assertFalse(cv2.CascadeClassifier(str(
                Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            )).empty())
        except ImportError:
            self.skipTest("opencv unavailable")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "black.mp4"
            p = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                                "color=c=black:s=640x360:r=10:d=5",
                                "-c:v", "mpeg4", "-y", str(src)], capture_output=True, timeout=25)
            self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace")[-1000:])
            result = inspect(src, 0, 5, self.FACE, layout="facecam_top",
                             source_width=640, source_height=360)
            self.assertEqual(result["status"], "review")
            self.assertEqual(result["samples"], 3)


if __name__ == "__main__":
    unittest.main()
