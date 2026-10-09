import unittest

from src.server.game_engine import GameEngine, WAITING_FOR_PLAYERS


class RematchAndResetTests(unittest.TestCase):
    def test_winner_is_highest_score(self):
        game = GameEngine()
        game.begin_match(["alice", "bob"], "alice")
        game.scores = {"alice": 4, "bob": 7}
        self.assertEqual(game.winner(), "bob")

    def test_reset_clears_all_match_data(self):
        game = GameEngine()
        game.begin_match(["alice", "bob"], "alice")
        game.add_pattern_step("c4")
        game.rematch_votes.add("alice")
        game.reset()
        self.assertEqual(game.state, WAITING_FOR_PLAYERS)
        self.assertEqual(game.players, [])
        self.assertEqual(game.scores, {})
        self.assertEqual(game.rematch_votes, set())


if __name__ == "__main__":
    unittest.main()

