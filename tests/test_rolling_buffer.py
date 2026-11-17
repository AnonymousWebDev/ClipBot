"""Tests for queued live clips preserving source segments across long render waits."""
import tempfile
import unittest
from pathlib import Path

from studio.rolling_buffer import prune


class RollingBufferTests(unittest.TestCase):
    def test_retains_queued_clip_even_if_outside_rolling_window(self):
        with tempfile.TemporaryDirectory() as root:
            entries = []
            for i in range(60):
                file = Path(root) / f"part{i:02d}.ts"
                file.write_bytes(b"segment")
                entries.append((file, i * 6.0, (i + 1) * 6.0))
            # Current stream time is 360s; keep last 120s ordinarily.
            # A source clip queued at 50s still needs segments [24s, 62s].
            pinned = {"clip001": (24.0, 62.0)}
            retained = prune(entries, keep_from=240.0, pinned=pinned)
            found = [int(x[0].stem[4:]) for x in retained]
            self.assertTrue(all(i in found for i in range(4, 11)))
            self.assertFalse(entries[2][0].exists())
            self.assertFalse(entries[15][0].exists())
            self.assertTrue(entries[6][0].exists())
            # Once lossless source copy finishes, unpinning permits cleanup.
            after = prune(retained, keep_from=240.0, pinned={})
            self.assertFalse(entries[6][0].exists())
            self.assertTrue(entries[55][0].exists())
            self.assertEqual(len(after), 20)

    def test_overlapping_pins_and_boundary_touch_do_not_keep_extra_files(self):
        with tempfile.TemporaryDirectory() as root:
            items = []
            for n in range(4):
                p = Path(root) / f"s{n}.ts"
                p.touch()
                items.append((p, 10.0 * n, 10.0 * (n + 1)))
            kept = prune(items, keep_from=45, pinned={"a": (4, 9), "b": (21, 29)})
            self.assertEqual([p.name for p, _, _ in kept], ["s0.ts", "s2.ts"])
            self.assertFalse(items[1][0].exists())
            self.assertFalse(items[3][0].exists())

    def test_new_segments_survive_window(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "recent.ts"
            p.touch()
            kept = prune([(p, 95, 102)], keep_from=90, pinned={})
            self.assertEqual(len(kept), 1)
            self.assertTrue(p.exists())


if __name__ == "__main__":
    unittest.main()
