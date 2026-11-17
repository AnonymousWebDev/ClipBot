"""Lightweight chat-based highlight signals. No AI service or transcription required.

The scoring function is deliberately independent of Twitch networking so it can be
tested with recorded chat traffic and later reused for Kick/YouTube chat adapters.
"""
import re
from collections.abc import Mapping

REACTIONS = re.compile(
    r"\\b(?:kekw|omegalul|lulw?|lmao|lol|rofl|pog(?:gers|champ)?|"
    r"wtf|holy|insane|no\\s+way|lets\\s+go)\\b", re.IGNORECASE
)


def parse_twitch_privmsg(line: bytes):
    """Return (username, text) for a Twitch IRC PRIVMSG, ignoring other events.

    Works with both ordinary IRC lines and IRCv3 tagged messages.
    """
    if b" PRIVMSG #" not in line:
        return None
    prefix, _, rest = line.partition(b" PRIVMSG #")
    sender = prefix.rsplit(b":", 1)[-1].split(b"!", 1)[0]
    _, separator, payload = rest.partition(b" :")
    if not separator or not sender:
        return None
    user = sender.decode("utf-8", "replace").strip().lower()
    if not user:
        return None
    return user, payload.decode("utf-8", "replace")


def reaction_count(message: str) -> int:
    """Count recognizable excitement/laughter tokens in one chat message."""
    return len(REACTIONS.findall(message[:500]))


def evaluate_chat_spike(
    counts: Mapping,
    unique_by_second: Mapping,
    reactions: Mapping,
    now: int,
    *,
    current_seconds: int = 8,
    baseline_seconds: int = 120,
    min_ratio: float = 3.0,
    min_rate: float = 1.5,
    min_messages: int = 15,
    min_unique: int = 4,
):
    """Score a chat spike against an earlier, non-overlapping baseline.

    Returns None for insufficient evidence. All timestamps are *stream seconds*,
    not wall-clock seconds. Missing seconds count as zero messages.
    """
    if now < baseline_seconds // 2:
        return None
    recent_start = now - current_seconds + 1
    baseline_end = recent_start - 5
    baseline_start = max(0, baseline_end - baseline_seconds)
    baseline_length = baseline_end - baseline_start
    if baseline_length < 30:
        return None

    current_total = sum(counts.get(t, 0) for t in range(recent_start, now + 1))
    current_rate = current_total / current_seconds
    if current_total < min_messages:
        return None

    unique = set()
    for second in range(recent_start, now + 1):
        unique.update(unique_by_second.get(second, ()))
    if len(unique) < min_unique:
        return None

    baseline_total = sum(counts.get(t, 0) for t in range(baseline_start, baseline_end))
    baseline_rate = baseline_total / baseline_length
    ratio = current_rate / max(baseline_rate, 0.25)
    if current_rate < min_rate or ratio < min_ratio:
        return None

    excitement = sum(reactions.get(t, 0) for t in range(recent_start, now + 1))
    # Prefer strong, broadly supported spikes over one chatter spamming emotes.
    score = min(100, round(
        40 + min(25, (ratio - min_ratio) * 8)
        + min(20, len(unique) * 1.5)
        + min(15, excitement * 1.5)
    ))
    return {
        "score": int(score),
        "time": int(now),
        "rate": round(current_rate, 2),
        "baseline": round(baseline_rate, 2),
        "ratio": round(ratio, 2),
        "unique_chatters": len(unique),
        "reactions": int(excitement),
    }
