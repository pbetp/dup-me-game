"""Offline practice: hear a short melody, play it back by ear, get typing-test style stats.

No server is involved. The first note of every melody is shown as a reference, so
the player finds the rest by interval. Every answered note is judged on the spot,
like a letter in a typing test, and the session reports accuracy, pitch precision
and speed. The given first note is never scored.
"""

from __future__ import annotations

import random
import time
from collections import Counter

from src.common.config import PIANO_KEYS, WHITE_KEYS

MIDI = {note[0]: note[2] for note in PIANO_KEYS}

# level: (notes per melody including the given first note, notes it may use,
#         largest jump in steps of that pool)
LEVELS = {
    "easy": (4, tuple(note[0] for note in WHITE_KEYS[:8]), 2),   # C4-C5, small steps
    "medium": (5, tuple(note[0] for note in WHITE_KEYS), 4),     # all white keys
    "hard": (6, tuple(note[0] for note in PIANO_KEYS), 16),      # all 17 keys, any leap
}
LENGTH_OPTIONS = (10, 20, 30)


def make_melody(level: str, rng: random.Random) -> list[str]:
    length, pool, leap = LEVELS[level]
    index = rng.randrange(len(pool))
    melody = [pool[index]]
    while len(melody) < length:
        index = rng.choice([i for i in range(index - leap, index + leap + 1) if 0 <= i < len(pool)])
        melody.append(pool[index])
    return melody


def closeness(expected: str, played: str) -> float:
    """1.0 for the exact note, losing 1/12 per semitone; an octave or more away scores 0."""
    return max(0.0, 1 - abs(MIDI[expected] - MIDI[played]) / 12)


class PracticeSession:
    def __init__(self, level: str = "medium", total: int = 10, rng: random.Random | None = None):
        if level not in LEVELS:
            raise ValueError("Unknown level")
        self.level, self.total = level, total
        self.rng = rng or random.Random()
        self.melodies: list[list[str]] = []
        # answers[i] holds the player's notes for melodies[i][1:] (the first note is given).
        self.answers: list[list[str]] = []
        self.replays = 0
        self.combo = self.best_combo = 0
        self.started_at = time.monotonic()
        self.answer_seconds = 0.0
        self._answer_started: float | None = None

    @property
    def current(self) -> list[str]:
        return list(self.melodies[-1]) if self.melodies else []

    @property
    def melody_done(self) -> bool:
        return bool(self.melodies) and len(self.answers[-1]) >= len(self.melodies[-1]) - 1

    @property
    def finished(self) -> bool:
        return len(self.melodies) >= self.total and self.melody_done

    def next_melody(self) -> list[str]:
        self.melodies.append(make_melody(self.level, self.rng))
        self.answers.append([])
        return self.current

    def start_answer(self, now: float | None = None) -> None:
        """The speed clock runs only while the player can answer (and through replays they ask for)."""
        if self._answer_started is None and not self.melody_done:
            self._answer_started = time.monotonic() if now is None else now

    def stop(self, now: float | None = None) -> None:
        if self._answer_started is not None:
            self.answer_seconds += (time.monotonic() if now is None else now) - self._answer_started
            self._answer_started = None

    def answer(self, color: str, now: float | None = None) -> bool:
        if not self.melodies or self.melody_done or color not in MIDI:
            return False
        melody, answers = self.melodies[-1], self.answers[-1]
        correct = color == melody[len(answers) + 1]
        answers.append(color)
        self.combo = self.combo + 1 if correct else 0
        self.best_combo = max(self.best_combo, self.combo)
        if self.melody_done:
            self.stop(now)
        return correct

    def stats(self, now: float | None = None) -> dict:
        pairs = [(note, played) for melody, answers in zip(self.melodies, self.answers)
                 for note, played in zip(melody[1:], answers)]
        correct = sum(note == played for note, played in pairs)
        misses = [(note, played) for note, played in pairs if note != played]
        seconds = self.answer_seconds
        if self._answer_started is not None:
            seconds += (time.monotonic() if now is None else now) - self._answer_started
        done = [(melody[1:], answers) for melody, answers in zip(self.melodies, self.answers)
                if len(answers) >= len(melody) - 1]
        return {
            "notes": len(pairs),
            "correct": correct,
            "accuracy": round(100 * correct / len(pairs)) if pairs else 0,
            "precision": round(100 * sum(closeness(*pair) for pair in pairs) / len(pairs)) if pairs else 0,
            # Correct notes per minute of answering time, like words per minute.
            "npm": round(correct * 60 / seconds) if seconds >= 1 else 0,
            "melodies": len(done),
            "perfect": sum(expected == answers for expected, answers in done),
            "combo": self.combo,
            "best_combo": self.best_combo,
            "replays": self.replays,
            "avg_miss": (sum(abs(MIDI[a] - MIDI[b]) for a, b in misses) / len(misses)) if misses else 0.0,
            "weakest": [note for note, _count in Counter(note for note, _played in misses).most_common(3)],
            "seconds": seconds,
        }
