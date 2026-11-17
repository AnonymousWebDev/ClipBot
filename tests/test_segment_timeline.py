"""CSV segment timestamps, reconnection, and audio/video clock regression tests."""
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path

from studio.segment_timeline import (
    index_rows, latest_video_time, continuous_tail, video_diagnostics,
)


class SegmentTimelineTests(unittest.TestCase):
    def test_twitch_hls_large_absolute_timestamps(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            for i in range(3):
                (folder / f"p01_{i:05d}.ts").write_bytes(b"segment")
            rows = [
                "p01_00000.ts,100000.0,100006.0",
                "p01_00001.ts,100006.0,100012.0",
                "p01_00002.ts,100012.0,100018.0",
            ]
            items, seen, origin = index_rows(rows, 0, 0, None, folder)
            self.assertEqual((seen, origin), (3, 100000.0))
            self.assertEqual([(start, end) for _, start, end in items],
                             [(0, 6), (6, 12), (12, 18)])
            self.assertEqual(continuous_tail(items), (0, 18))
            self.assertEqual(video_diagnostics(20, latest_video_time(items), items)["video_lag_sec"], 2)

    def test_reconnect_maps_second_process_to_its_actual_start(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "p02_00000.ts").write_bytes(b"video")
            rows = ["p02_00000.ts,4100.0,4106.0"]
            got, seen, origin = index_rows(rows, 0, 130.0, None, folder)
            self.assertEqual((seen, origin), (1, 4100.0))
            self.assertEqual((got[0][1], got[0][2]), (130, 136))

    def test_incomplete_row_is_retried_when_segment_is_ready(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            first = folder / "p01_00000.ts"
            first.write_bytes(b"valid")
            rows = ["p01_00000.ts,0,6", "p01_00001.ts,6,"]
            got, seen, origin = index_rows(rows, 0, 0, None, folder)
            self.assertEqual((len(got), seen, origin), (1, 1, 0.0))
            second = folder / "p01_00001.ts"
            second.write_bytes(b"valid")
            rows[-1] = "p01_00001.ts,6,12"
            added, seen, origin = index_rows(rows, seen, 0, origin, folder)
            self.assertEqual((len(added), seen), (1, 2))
            self.assertEqual(added[0][1:], (6.0, 12.0))

    def test_video_gap_does_not_claim_continuous_footage(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            files = [folder / f"p01_{i:05d}.ts" for i in range(4)]
            for f in files:
                f.write_bytes(b"data")
            indexed = [(files[0], 0.0, 6.0), (files[1], 6.0, 12.0),
                       (files[2], 150.0, 156.0), (files[3], 156.0, 162.0)]
            self.assertEqual(continuous_tail(indexed), (150.0, 162.0))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg unavailable")
    def test_real_ffmpeg_segment_csv_is_indexable(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            cmd = [
                "ffmpeg", "-nostdin", "-v", "error",
                "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=12",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "mpeg2video", "-g", "24", "-c:a", "mp2", "-t", "14",
                "-f", "segment", "-segment_time", "6", "-reset_timestamps", "1",
                "-segment_format", "mpegts", "-segment_list", "p01.csv",
                "-segment_list_type", "csv", "p01_%05d.ts",
                "-map", "1:a:0", "-vn", "-ac", "1", "-ar", "16000", "-t", "14",
                "-f", "s16le", "pipe:1",
            ]
            p = subprocess.run(cmd, cwd=folder, stdout=subprocess.DEVNULL,
                               capture_output=False, timeout=35)
            self.assertEqual(p.returncode, 0)
            lines = (folder / "p01.csv").read_text().splitlines()
            found, seen, origin = index_rows(lines, 0, 0, None, folder)
            self.assertEqual(seen, len(lines))
            self.assertGreaterEqual(latest_video_time(found), 13.0)
            self.assertGreaterEqual(continuous_tail(found)[1] - continuous_tail(found)[0], 13.0)


if __name__ == "__main__":
    unittest.main()
