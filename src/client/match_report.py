"""Local, post-match review. Never used for scoring or live pattern hints."""
from __future__ import annotations
import csv
from pathlib import Path


def review_rounds(rounds, scores):
    """One entry per round: who played which role, the score, and each step's verdict."""
    names = {row['id']: row['nickname'] for row in scores}
    result = []
    for event in rounds:
        pattern, answers = event['pattern'], event['answers']
        repeater_id = event['repeater_id']
        creator = next((name for player_id, name in names.items() if player_id != repeater_id), 'Creator')
        steps = []
        for index, note in enumerate(pattern):
            answer = answers[index] if index < len(answers) else None
            verdict = 'OK' if answer == note else 'MISSED' if answer is None else 'WRONG'
            steps.append((index + 1, note, answer, verdict))
        correct = sum(verdict == 'OK' for *_rest, verdict in steps)
        result.append({
            'round': event['round'], 'creator': creator, 'repeater': names.get(repeater_id, 'Repeater'),
            'correct': correct, 'total': len(pattern),
            'accuracy': f'{100 * correct / len(pattern):.0f}%' if pattern else 'N/A (empty pattern)',
            'steps': steps,
        })
    return result


def review_text(rounds, scores):
    lines = ['MATCH REVIEW', '', *[f"{row['nickname']}: {row['score']} points" for row in scores], '']
    for entry in review_rounds(rounds, scores):
        lines.extend([f"ROUND {entry['round']} · {entry['repeater']}",
                      f"{entry['correct']}/{entry['total']} correct · Accuracy {entry['accuracy']}",
                      'Step   Pattern  Answer   Result'])
        for step, note, answer, verdict in entry['steps']:
            lines.append(f'{step:>4}   {note.upper():<7}  {(answer or "—").upper():<7}  {verdict}')
        lines.append('')
    return '\n'.join(lines)


def _spreadsheet_text(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def export_csv(path, rounds, scores):
    """Export one row per pattern position plus a final score table."""
    names = {row['id']: row['nickname'] for row in scores}
    with Path(path).open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        writer.writerow(['Round', 'Repeater', 'Step', 'Expected note', 'Answer', 'Correct'])
        for event in rounds:
            pattern, answers = event['pattern'], event['answers']
            for index, note in enumerate(pattern):
                answer = answers[index] if index < len(answers) else ''
                writer.writerow([event['round'], _spreadsheet_text(names.get(event['repeater_id'], 'Repeater')),
                                 index + 1, note, answer, int(note == answer)])
            if not pattern:
                writer.writerow([event['round'], _spreadsheet_text(names.get(event['repeater_id'], 'Repeater')), '', '(empty pattern)', '', 0])
        writer.writerow([])
        writer.writerow(['Player', 'Final score'])
        for row in scores:
            writer.writerow([_spreadsheet_text(row['nickname']), row['score']])
