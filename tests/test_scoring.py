import unittest

from src.server.game_engine import GameEngine


class ScoringTests(unittest.TestCase):
    def test_only_matching_positions_score(self):
        game = GameEngine()
        game.begin_match(["alice", "bob"], "alice")
        for color in ("c4", "d4", "e4", "f4"):
            game.add_pattern_step(color)
        game.begin_repeat()
        for color in ("c4", "d4", "f4", "f4"):
            game.add_answer(color)
        self.assertEqual(game.round_points(), 3)
        self.assertEqual(game.scores["bob"], 3)


if __name__ == "__main__":
    unittest.main()

