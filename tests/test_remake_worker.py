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

    def test_missing_chat_transcript_is_generated_during_render(self):
        with tempfile.TemporaryDirectory() as d:
            job = {"kind": "live", "dir": d}
            self.assertEqual(jobs._words_for_remake(job, {"captions": True}), [])

    def test_available_transcript_works(self):
        with tempfile.TemporaryDirectory() as d:
            words = [{"w": "hi", "s": 0.0, "e": 0.4}]
            (Path(d) / "words.json").write_text(json.dumps(words), encoding="utf-8")
            self.assertEqual(jobs._words_for_remake({"kind": "video", "dir": d},
                                                    {"captions": True}), words)

    def test_live_missing_transcript_can_enable_captions_on_remake(self):
        with tempfile.TemporaryDirectory() as d:
            clip = {"id": "clip1", "status": "done", "start": 0.0, "end": 30.0,
                    "captions": False, "layout": "blur", "style": "bounce"}
            job = {"kind": "live", "dir": d, "clips": [clip]}
            with mock.patch.object(jobs, "_jobs", {"test-job": job}), \
                 mock.patch.object(jobs, "save"), \
                 mock.patch.object(jobs._q, "put") as queued:
                jobs.request_render("test-job", "clip1", {"captions": True})
            self.assertEqual(clip["status"], "queued")
            self.assertTrue(clip["captions"])
            queued.assert_called_once_with(("clip", "test-job", "clip1"))

    def test_chat_clip_transcribes_only_once_and_keeps_source_relative_timing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "clips").mkdir()
            src = root / "clips" / "clip1.src.ts"
            src.write_bytes(b"video")
            clip = {"id": "clip1", "captions": True}
            job = {"kind": "live", "dir": d}
            expected = [{"w": "Hello", "s": 5.2, "e": 5.7},
                        {"w": "world!", "s": 12.5, "e": 13.1}]
            with mock.patch.object(jobs.media, "extract_audio") as extract, \
                 mock.patch.object(jobs.media, "load_audio", return_value=[1, 2]), \
                 mock.patch.object(jobs.transcribe, "transcribe", return_value=expected) as speech, \
                 mock.patch.object(jobs.brain, "english_captions", side_effect=AssertionError("paid AI used")):
                first = jobs._live_caption_words(job, clip, src, 5.0, 10.0)
                second = jobs._live_caption_words(job, clip, src, 10.0, 15.0)
            self.assertEqual(first, [expected[0]])
            self.assertEqual(second, [expected[1]])
            self.assertEqual(speech.call_count, 1)
            self.assertEqual(extract.call_count, 1)
            self.assertTrue((root / "clips" / "clip1.speech.json").exists())

    def test_chat_clip_retranscribes_after_source_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "clips").mkdir()
            src = root / "clips" / "clip1.src.ts"
            src.write_bytes(b"before")
            clip = {"id": "clip1"}
            with mock.patch.object(jobs.media, "extract_audio"), \
                 mock.patch.object(jobs.media, "load_audio", return_value=[1]), \
                 mock.patch.object(jobs.transcribe, "transcribe", return_value=[]) as speech:
                jobs._live_caption_words({"kind": "live", "dir": d}, clip, src, 0, 30)
                src.write_bytes(b"after the source was replaced")
                jobs._live_caption_words({"kind": "live", "dir": d}, clip, src, 0, 30)
            self.assertEqual(speech.call_count, 2)

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
