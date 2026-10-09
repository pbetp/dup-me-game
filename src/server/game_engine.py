"""Pure game rules that are easy to unit test."""

from __future__ import annotations

from dataclasses import dataclass, field
from src.common.config import DEFAULT_ROUNDS, ROUND_OPTIONS


WAITING_FOR_PLAYERS = "WAITING_FOR_PLAYERS"
ROUND_1_CREATE = "ROUND_1_CREATE"
ROUND_1_REPEAT = "ROUND_1_REPEAT"
ROUND_2_CREATE = "ROUND_2_CREATE"
ROUND_2_REPEAT = "ROUND_2_REPEAT"
MATCH_RESULTS = "MATCH_RESULTS"
WAITING_FOR_REMATCH = "WAITING_FOR_REMATCH"


@dataclass
class GameEngine:
    total_rounds: int = DEFAULT_ROUNDS
    state: str = WAITING_FOR_PLAYERS
    round_number: int = 0
    players: list[str] = field(default_factory=list)
    first_creator: str | None = None
    creator: str | None = None
    repeater: str | None = None
    pattern: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)
    rematch_votes: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if type(self.total_rounds) is not int or self.total_rounds not in ROUND_OPTIONS:
            raise ValueError(f"Rounds must be one of {ROUND_OPTIONS}")

    @property
    def is_creating(self) -> bool:
        return self.state.endswith("_CREATE")

    @property
    def is_repeating(self) -> bool:
        return self.state.endswith("_REPEAT")

    def begin_match(self, players: list[str], first_creator: str) -> None:
        if len(players) != 2 or first_creator not in players:
            raise ValueError("A match requires exactly two players and a valid creator")
        self.players = list(players)
        self.first_creator = first_creator
        self.scores = {player_id: 0 for player_id in players}
        self.rematch_votes.clear()
        self.begin_creation(1)

    def begin_creation(self, round_number: int) -> None:
        if not 1 <= round_number <= self.total_rounds:
            raise ValueError(f"Round number must be from 1 to {self.total_rounds}")
        if len(self.players) != 2 or self.first_creator is None:
            raise RuntimeError("Match has not been initialized")
        self.round_number = round_number
        if round_number % 2 == 1:
            self.creator = self.first_creator
        else:
            self.creator = next(player for player in self.players if player != self.first_creator)
        self.repeater = next(player for player in self.players if player != self.creator)
        self.pattern = []
        self.answers = []
        self.state = f"ROUND_{round_number}_CREATE"

    def begin_repeat(self) -> None:
        self.answers = []
        self.state = f"ROUND_{self.round_number}_REPEAT"

    def add_pattern_step(self, color: str) -> None:
        self.pattern.append(color)

    def add_answer(self, color: str) -> bool:
        index = len(self.answers)
        if index >= len(self.pattern):
            raise RuntimeError("The pattern is already complete")
        self.answers.append(color)
        correct = color == self.pattern[index]
        if correct and self.repeater is not None:
            self.scores[self.repeater] += 1
        return correct

    def round_points(self) -> int:
        return sum(expected == actual for expected, actual in zip(self.pattern, self.answers))

    def winner(self) -> str | None:
        if len(self.players) != 2:
            return None
        first, second = self.players
        if self.scores[first] == self.scores[second]:
            return None
        return first if self.scores[first] > self.scores[second] else second

    def reset(self) -> None:
        self.state = WAITING_FOR_PLAYERS
        self.round_number = 0
        self.players = []
        self.first_creator = None
        self.creator = None
        self.repeater = None
        self.pattern = []
        self.answers = []
        self.scores = {}
        self.rematch_votes.clear()
