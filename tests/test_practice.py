import random
import unittest

from src.client.practice import LEVELS, MIDI, PracticeSession, closeness, make_melody


class PracticeTests(unittest.TestCase):
    def test_melodies_follow_each_level(self):
        rng = random.Random(7)
        for level, (length, pool, leap) in LEVELS.items():
            for _ in range(50):
                melody = make_melody(level, rng)
                self.assertEqual(len(melody), length)
                self.assertTrue(set(melody) <= set(pool))
                for a, b in zip(melody, melody[1:]):
                    self.assertLessEqual(abs(pool.index(a) - pool.index(b)), leap)

    def test_closeness_rewards_near_misses(self):
        self.assertEqual(closeness("c4", "c4"), 1)
        self.assertAlmostEqual(closeness("c4", "cs4"), 11 / 12)
        self.assertEqual(closeness("c4", "c5"), 0)

    def test_first_note_is_given_and_never_scored(self):
        session = PracticeSession("easy", total=1, rng=random.Random(3))
        melody = session.next_melody()
        for note in melody[1:]:
            self.assertTrue(session.answer(note, now=0))
        self.assertTrue(session.finished)
        self.assertEqual(session.stats()["notes"], len(melody) - 1)

    def test_stats_like_a_typing_test(self):
        session = PracticeSession("easy", total=2, rng=random.Random(1))
        first = session.next_melody()
        session.start_answer(now=0)
        for note in first[1:]:
            self.assertTrue(session.answer(note, now=0))
        self.assertTrue(session.melody_done)
        self.assertFalse(session.finished)
        second = session.next_melody()
        session.start_answer(now=10)
        wrong = next(n for n in MIDI if n != second[1])
        self.assertFalse(session.answer(wrong, now=11))
        for note in second[2:]:
            session.answer(note, now=12)
        self.assertTrue(session.finished)
        self.assertFalse(session.answer("c4"))  # nothing left to answer
        stats = session.stats()
        self.assertEqual((stats["notes"], stats["correct"]), (6, 5))
        self.assertEqual(stats["accuracy"], 83)
        self.assertGreater(stats["precision"], stats["accuracy"] - 1)
        self.assertEqual((stats["perfect"], stats["melodies"]), (1, 2))
        self.assertEqual(stats["best_combo"], 3)
        self.assertEqual(stats["weakest"], [second[1]])
        self.assertEqual(stats["avg_miss"], abs(MIDI[second[1]] - MIDI[wrong]))
        self.assertEqual(stats["seconds"], 2)
        self.assertEqual(stats["npm"], 150)

    def test_unknown_level_is_rejected(self):
        with self.assertRaises(ValueError):
            PracticeSession("expert")


if __name__ == "__main__":
    unittest.main()
