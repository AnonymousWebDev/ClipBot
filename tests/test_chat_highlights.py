"""Regression tests for chat-driven highlight detection (no live Twitch required)."""
import unittest
from collections import Counter

from studio.chat_highlights import evaluate_chat_spike, parse_twitch_privmsg, reaction_count


class ChatHighlightTests(unittest.TestCase):
    def test_parse_regular_twitch_chat(self):
        raw = b":SomeViewer!someviewer@someviewer.tmi.twitch.tv PRIVMSG #streamer :KEKW what happened"
        self.assertEqual(parse_twitch_privmsg(raw), ("someviewer", "KEKW what happened"))

    def test_parse_tagged_twitch_chat(self):
        raw = b"@badge-info=;badges= :Viewer!viewer@viewer.tmi.twitch.tv PRIVMSG #streamer :NO WAY"
        self.assertEqual(parse_twitch_privmsg(raw), ("viewer", "NO WAY"))
        self.assertIsNone(parse_twitch_privmsg(b"PING :tmi.twitch.tv"))

    def test_emote_detection(self):
        self.assertGreaterEqual(reaction_count("KEKW OMEGALUL no way"), 3)
        self.assertEqual(reaction_count("normal conversation"), 0)

    def test_high_activity_detects_spike(self):
        counts = Counter({i: 2 for i in range(10, 185)})
        users = {}
        for i in range(193, 201):
            counts[i] = 14
            users[i] = {"alice", "bob", "carol", "dave", "ellen"}
        out = evaluate_chat_spike(counts, users, Counter({200: 9}), 200)
        self.assertIsNotNone(out)
        self.assertGreaterEqual(out["ratio"], 3)
        self.assertGreaterEqual(out["score"], 40)
        self.assertEqual(out["unique_chatters"], 5)

    def test_no_spike_at_normal_rate(self):
        counts = Counter({i: 4 for i in range(201)})
        users = {i: {"a", "b", "c", "d"} for i in range(190, 201)}
        self.assertIsNone(evaluate_chat_spike(counts, users, {}, 200))

    def test_spam_from_one_user_ignored(self):
        counts = Counter({i: 1 for i in range(10, 185)})
        users = {}
        for i in range(193, 201):
            counts[i] = 100
            users[i] = {"oneperson"}
        self.assertIsNone(evaluate_chat_spike(counts, users, {}, 200))

    def test_warmup_and_low_volume_ignored(self):
        self.assertIsNone(evaluate_chat_spike({70: 20}, {70: {"a", "b", "c", "d"}}, {}, 70))
        self.assertIsNone(evaluate_chat_spike({200: 1}, {200: {"a", "b", "c", "d"}}, {}, 200))


if __name__ == "__main__":
    unittest.main()
