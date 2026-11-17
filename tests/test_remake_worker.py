"""Regression tests for live re-renders that used to stay on Preparing clip."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from studio import jobs


class RemakeWorkerTests(unittest.TestCase):
    def test_chat_only_remake_without_captions_needs_no_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            job = {"kind": "live", "dir": d}
            self.assertEqual(jobs._words_for_remake(job, {"captions": False}), [])

    def test_missing_chat_transcript_shows_actionable_error(self):
        with tempfile.TemporaryDirectory() as d:
            job = {"kind": "live", "dir": d}
            with self.assertRaisesRegex(ValueError, "Turn off Generate captions"):
                jobs._words_for_remake(job, {"captions": True})

    def test_available_transcript_works(self):
        with tempfile.TemporaryDirectory() as d:
            words = [{"w": "hi", "s": 0.0, "e": 0.4}]
            (Path(d) / "words.json").write_text(json.dumps(words), encoding="utf-8")
            self.assertEqual(jobs._words_for_remake({"kind": "video", "dir": d},
                                                    {"captions": True}), words)

    def test_live_missing_transcript_rejected_before_queueing(self):
        with tempfile.TemporaryDirectory() as d:
            clip = {"id": "clip1", "status": "done", "start": 0.0, "end": 30.0,
                    "captions": False, "layout": "blur", "style": "bounce"}
            job = {"kind": "live", "dir": d, "clips": [clip]}
            with mock.patch.object(jobs, "_jobs", {"test-job": job}):
                with self.assertRaisesRegex(ValueError, "Turn off Generate captions"):
                    jobs.request_render("test-job", "clip1", {"captions": True})
            self.assertEqual(clip["status"], "done")

    def test_quick_worker_marks_error_if_dispatch_crashes(self):
        class OneJob:
            def __init__(self):
                self.get_count = 0

            def get(self, quick_only=False):
                if self.get_count:
                    raise StopIteration
                self.get_count += 1
                return ("clip", "test-job", "clip1")

        with tempfile.TemporaryDirectory() as d:
            clip = {"id": "clip1", "status": "queued", "captions": False}
            job = {"id": "test-job", "dir": d, "user": "u_test01",
                   "clips": [clip]}
            saved = []
            with mock.patch.object(jobs, "_q", OneJob()), \
                 mock.patch.object(jobs, "_jobs", {"test-job": job}), \
                 mock.patch.object(jobs, "render_one", side_effect=RuntimeError("encoder crashed")), \
                 mock.patch.object(jobs, "save", side_effect=lambda j: saved.append(clip["status"])):
                with self.assertRaises(StopIteration):
                    jobs._worker(quick_only=True)
            self.assertEqual(clip["status"], "error")
            self.assertIn("encoder crashed", clip["error"])
            self.assertIn("error", saved)
            self.assertTrue((Path(d) / "error.log").exists())


if __name__ == "__main__":
    unittest.main()
