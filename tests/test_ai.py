import unittest

from src.bot.difficulty_model import DifficultyModel


class DifficultyModelTests(unittest.TestCase):
    def test_increases_for_strong_human(self):
        model = DifficultyModel(level="medium", human_accuracy=0.95)
        self.assertEqual(model.observe_match("loss"), "hard")

    def test_decreases_after_repeated_bot_wins(self):
        model = DifficultyModel(level="hard", human_accuracy=0.7)
        model.observe_match("win")
        self.assertEqual(model.observe_match("win"), "medium")


if __name__ == "__main__":
    unittest.main()
