import unittest
from src.common.config import ROUND_OPTIONS

from src.server.game_engine import GameEngine, ROUND_1_CREATE, ROUND_2_CREATE


class GameEngineTests(unittest.TestCase):
    def setUp(self):
        self.game = GameEngine()
        self.game.begin_match(["p1", "p2"], "p1")

    def test_roles_switch(self):
        self.assertEqual(self.game.state, ROUND_1_CREATE)
        self.assertEqual(self.game.creator, "p1")
        self.game.begin_creation(2)
        self.assertEqual(self.game.state, ROUND_2_CREATE)
        self.assertEqual(self.game.creator, "p2")

    def test_score_each_correct_position(self):
        self.game.add_pattern_step("c4")
        self.game.add_pattern_step("d4")
        self.game.add_pattern_step("e4")
        self.game.begin_repeat()
        self.assertTrue(self.game.add_answer("c4"))
        self.assertFalse(self.game.add_answer("f4"))
        self.assertTrue(self.game.add_answer("e4"))
        self.assertEqual(self.game.scores["p2"], 2)

    def test_draw_has_no_winner(self):
        self.assertIsNone(self.game.winner())

    def test_each_round_option_alternates_roles_and_accumulates_scores(self):
        for total in ROUND_OPTIONS:
            with self.subTest(total=total):
                game = GameEngine(total_rounds=total)
                game.begin_match(["p1", "p2"], "p1")
                for number in range(1, total + 1):
                    game.begin_creation(number)
                    self.assertEqual(game.creator, "p1" if number % 2 else "p2")
                    self.assertEqual(game.state, f"ROUND_{number}_CREATE")
                    game.add_pattern_step("ds5")
                    game.begin_repeat()
                    self.assertTrue(game.is_repeating)
                    self.assertTrue(game.add_answer("ds5"))
                self.assertEqual(game.scores, {"p1": total // 2, "p2": total // 2})
                with self.assertRaises(ValueError):
                    game.begin_creation(total + 1)
                game.reset()
                self.assertEqual(game.total_rounds, total)
                game.begin_match(["p1", "p2"], "p2")
                self.assertEqual(game.round_number, 1)

    def test_invalid_round_counts_are_rejected(self):
        for count in (0, 1, 3, 13, 100, "4", 4.0, True):
            with self.subTest(count=count), self.assertRaises(ValueError):
                GameEngine(total_rounds=count)


if __name__ == "__main__":
    unittest.main()

