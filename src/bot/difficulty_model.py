"""Small explainable adaptive model; no external AI service is needed."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


LEVELS = ("easy", "medium", "hard")


@dataclass
class DifficultyModel:
    level: str = "medium"
    recent_results: list[str] = field(default_factory=list)
    human_accuracy: float = 0.75
    average_response_time: float = 1.0
    longest_pattern: int = 0
    missed_colors: Counter[str] = field(default_factory=Counter)

    def observe_human_round(
        self,
        pattern: list[str],
        answers: list[str],
        response_time: float | None = None,
    ) -> None:
        correct = sum(a == b for a, b in zip(pattern, answers))
        self.human_accuracy = correct / len(pattern) if pattern else 0.0
        self.longest_pattern = max(self.longest_pattern, len(pattern))
        for expected, actual in zip(pattern, answers):
            if expected != actual:
                self.missed_colors[expected] += 1
        if response_time is not None:
            self.average_response_time = response_time

    def observe_match(self, bot_result: str) -> str:
        if bot_result not in {"win", "loss", "draw"}:
            raise ValueError("Result must be win, loss, or draw")
        self.recent_results.append(bot_result)
        self.recent_results = self.recent_results[-3:]

        index = LEVELS.index(self.level)
        human_is_strong = self.human_accuracy >= 0.85 or self.recent_results.count("loss") >= 2
        human_needs_help = self.human_accuracy < 0.60 or self.recent_results.count("win") >= 2
        if human_is_strong and index < len(LEVELS) - 1:
            self.level = LEVELS[index + 1]
        elif human_needs_help and index > 0:
            self.level = LEVELS[index - 1]
        return self.level

    def pattern_length_range(self) -> tuple[int, int]:
        return {"easy": (3, 5), "medium": (5, 8), "hard": (8, 12)}[self.level]

    def accuracy_range(self) -> tuple[float, float]:
        return {"easy": (0.60, 0.70), "medium": (0.75, 0.85), "hard": (0.90, 1.0)}[self.level]

    def press_delay(self) -> float:
        return {"easy": 0.75, "medium": 0.50, "hard": 0.30}[self.level]

    def explanation(self) -> str:
        missed = self.missed_colors.most_common(1)
        missed_text = missed[0][0] if missed else "none yet"
        return (
            f"difficulty={self.level}; human accuracy={self.human_accuracy:.0%}; "
            f"longest pattern={self.longest_pattern}; most missed={missed_text}"
        )

