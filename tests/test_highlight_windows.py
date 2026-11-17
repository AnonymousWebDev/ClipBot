"""Regression tests for short highlights on live streams and uploaded VODs."""
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

import numpy as np

from studio import brain, live


class HighlightWindowTests(unittest.TestCase):
    def test_vod_window_is_30_seconds_and_follows_5_plus_25(self):
        self.assertEqual(brain.moment_window(40, 90, 5, 25), (35, 65))
        self.assertEqual(brain.moment_window(2, 90, 5, 25), (0, 30))
        self.assertEqual(brain.moment_window(88, 90, 5, 25), (60, 90))
        self.assertEqual(brain.moment_window(10, 20, 5, 25), (0, 20))

    def test_loudness_fallback_picks_30_seconds_around_peak(self):
        words = [{"w": f"word{i}", "s": i * 3.0, "e": i * 3.0 + .4}
                 for i in range(30)]
        loudness = np.full(90, -35.0)
        loudness[40] = -2.0
        with mock.patch.object(brain, "ask_ai", side_effect=RuntimeError("No AI configured")):
            clips, info = brain.find_clips(words, loudness, 90, max_clips=1,
                                           min_len=15, max_len=30, log=lambda _: None,
                                           fixed_vod=True)
        self.assertEqual(len(clips), 1)
        self.assertEqual((clips[0]["start"], clips[0]["end"]), (35, 65))
        self.assertIsNone(info["model"])

    def test_vod_ai_proposal_longer_than_30_is_trimmed_on_loudest_second(self):
        words = [{"w": f"word{i}", "s": i * 3.0, "e": i * 3.0 + .4}
                 for i in range(30)]
        loudness = np.full(90, -35.0)
        loudness[52] = -2.0
        candidate = {"start": 20, "end": 70, "score": 85, "hook": "WOW",
                     "title": "A moment", "description": "", "hashtags": []}
        with mock.patch.object(brain, "ask_ai", return_value=([candidate], "mock-model", 10)):
            clips, _ = brain.find_clips(words, loudness, 90, max_clips=1,
                                        min_len=15, max_len=30, log=lambda _: None,
                                        fixed_vod=True)
        self.assertEqual((clips[0]["start"], clips[0]["end"]), (47, 77))

    def _session(self, folder, *, mode="chat"):
        job = {"id": "job1", "dir": str(folder), "source": {"url": "https://twitch.tv/example"},
               "creator": "example", "title": "stream", "uploader": "example",
               "clips": [], "ai": {}, "options": {"captions": True}}
        settings = {"highlight_mode": mode, "min_gap_min": 2, "live_per_hour": 4,
                    "buffer_min": 3, "ai_every_min": 3, "min_len": 15, "max_len": 60,
                    "must_clip_min": 0, "min_score": 70, "decide_mode": "both"}
        return live.Session(job, settings)

    def test_chat_spike_creates_25_second_highlight(self):
        with tempfile.TemporaryDirectory() as d:
            session = self._session(Path(d))
            session.samples = live.SR * 200
            session.chat = Counter({i: 2 for i in range(10, 185)})
            session.chat_users = {}
            for i in range(193, 201):
                session.chat[i] = 14
                session.chat_users[i] = {"alice", "bob", "carol", "dave", "ellen"}
            session._chat_only_step()
            self.assertEqual(len(session.manual), 1)
            clip = session.manual[0]
            self.assertEqual((clip["start"], clip["end"]), (181.0, 206.0))

    def test_ai_live_highlight_uses_reaction_center(self):
        with tempfile.TemporaryDirectory() as d:
            session = self._session(Path(d), mode="ai")
            session.t_done = 200
            session.words = [{"w": f"word{i}", "s": 100 + i * 2, "e": 100 + i * 2 + .4}
                             for i in range(40)]
            session.db = [-30] * 200
            candidate = {"start": 150, "end": 180, "score": 90, "reason": "reaction"}
            signal = {"start": 166, "end": 168, "score": 95}
            produced = []
            with mock.patch.object(brain, "judge_transcript", return_value=([candidate], 0)), \
                 mock.patch.object(brain, "judge_signals", return_value=([signal], 0)), \
                 mock.patch.object(session, "_add_clip", side_effect=lambda c: produced.append(dict(c))):
                session._ai_check()
            self.assertEqual(len(produced), 1)
            self.assertEqual((produced[0]["start"], produced[0]["end"]), (152.0, 177.0))

    def test_manual_live_clip_length_is_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            session = self._session(Path(d))
            session.samples = 200 * live.SR
            segment = session.buf / "p01_00000.ts"
            segment.write_bytes(b"video")
            session.segments = [(segment, 160.0, 200.0)]
            session.clip_last(30)
            self.assertEqual((session.manual[-1]["start"], session.manual[-1]["end"]), (170.0, 200.0))


if __name__ == "__main__":
    unittest.main()
