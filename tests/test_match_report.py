import csv
import tempfile
import unittest
from pathlib import Path
from src.client.match_report import review_text, export_csv


class MatchReportTests(unittest.TestCase):
    def test_review_and_export_include_wrong_and_missing_answers(self):
        rounds = [{'round': 1, 'pattern': ['c4', 'd4', 'e4'], 'answers': ['c4', 'e4'], 'repeater_id': 'a'}]
        scores = [{'id': 'a', 'nickname': '=unsafe', 'score': 1}]
        text = review_text(rounds, scores)
        for expected in ('1/3 correct', '33%', 'WRONG', 'MISSED'):
            self.assertIn(expected, text)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'match.csv'
            export_csv(path, rounds, scores)
            with path.open(encoding='utf-8-sig') as file:
                rows = list(csv.reader(file))
            self.assertEqual([row[5] for row in rows[1:4]], ['1', '0', '0'])
            self.assertEqual(rows[1][1], "'=unsafe")

    def test_empty_round_has_no_division_by_zero(self):
        self.assertIn('N/A', review_text([{'round': 1, 'pattern': [], 'answers': [], 'repeater_id': 'a'}], []))
