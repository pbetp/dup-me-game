"""Co-op boss fight rules: two players repeat the boss's phrases to damage it.

Each phrase, the boss plays a short melody for every player who is still
standing. Players then repeat their own melody from memory: a correct note
deals 1 damage to the boss, a wrong note costs that player 1 HP, and notes
left unplayed when the timer ends count as wrong. A player on 0 HP sits out.
The team wins when the boss reaches 0 HP and loses when both players are out.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from src.common.config import (BOSS_MAX_HP, BOSS_PHRASE_MAX, BOSS_PHRASE_START,
                               DEFAULT_ROUNDS, PLAYER_MAX_HP, WHITE_KEYS)
from .game_engine import WAITING_FOR_PLAYERS

BOSS_SHOW = "BOSS_SHOW"
BOSS_REPEAT = "BOSS_REPEAT"

PHRASE_POOL = tuple(note[0] for note in WHITE_KEYS)
MAX_LEAP = 3


def phrase_length(number: int) -> int:
    return min(BOSS_PHRASE_MAX, BOSS_PHRASE_START + number - 1)


def make_phrase(length: int, rng: random.Random) -> list[str]:
    """A white-key melody that moves by small steps and never repeats a note back to back."""
    index = rng.randrange(len(PHRASE_POOL))
    phrase = [PHRASE_POOL[index]]
    while len(phrase) < length:
        index = rng.choice([i for i in range(index - MAX_LEAP, index + MAX_LEAP + 1)
                            if 0 <= i < len(PHRASE_POOL) and i != index])
        phrase.append(PHRASE_POOL[index])
    return phrase


@dataclass
class BossEngine:
    # total_rounds is unused by the rules; the shared server code reports it.
    total_rounds: int = DEFAULT_ROUNDS
    boss_max_hp: int = BOSS_MAX_HP
    player_max_hp: int = PLAYER_MAX_HP
    rng: random.Random = field(default_factory=random.Random)
    state: str = WAITING_FOR_PLAYERS
    round_number: int = 0
    players: list[str] = field(default_factory=list)
    boss_hp: int = 0
    hp: dict[str, int] = field(default_factory=dict)
    # Total damage each player has dealt to the boss this match.
    scores: dict[str, int] = field(default_factory=dict)
    phrases: dict[str, list[str]] = field(default_factory=dict)
    answers: dict[str, list[str]] = field(default_factory=dict)
    rematch_votes: set[str] = field(default_factory=set)
    # The dashboard shows creator/repeater for 1v1; nobody holds those roles here.
    creator: str | None = None
    repeater: str | None = None

    @property
    def is_creating(self) -> bool:
        return self.state == BOSS_SHOW

    @property
    def is_repeating(self) -> bool:
        return self.state == BOSS_REPEAT

    @property
    def boss_defeated(self) -> bool:
        return bool(self.players) and self.boss_hp <= 0

    @property
    def team_defeated(self) -> bool:
        return bool(self.players) and all(self.hp[player] <= 0 for player in self.players)

    def begin_match(self, players: list[str]) -> None:
        if len(players) != 2:
            raise ValueError("A boss fight requires exactly two players")
        self.players = list(players)
        self.boss_hp = self.boss_max_hp
        self.hp = {player: self.player_max_hp for player in players}
        self.scores = {player: 0 for player in players}
        self.rematch_votes.clear()
        self.begin_phrase(1)

    def begin_phrase(self, number: int) -> None:
        if not self.players:
            raise RuntimeError("Match has not been initialized")
        self.round_number = number
        length = phrase_length(number)
        # Knocked-out players get an empty phrase and simply watch.
        self.phrases = {player: make_phrase(length, self.rng) if self.hp[player] > 0 else []
                        for player in self.players}
        self.answers = {player: [] for player in self.players}
        self.state = BOSS_SHOW

    def begin_repeat(self) -> None:
        self.state = BOSS_REPEAT

    def can_answer(self, player: str) -> bool:
        return (self.is_repeating and player in self.players and self.hp[player] > 0
                and not self.boss_defeated and len(self.answers[player]) < len(self.phrases[player]))

    def add_answer(self, player: str, color: str) -> bool:
        if not self.can_answer(player):
            raise RuntimeError("This player cannot answer now")
        index = len(self.answers[player])
        self.answers[player].append(color)
        correct = color == self.phrases[player][index]
        if correct:
            self.boss_hp = max(0, self.boss_hp - 1)
            self.scores[player] += 1
        else:
            self.hp[player] = max(0, self.hp[player] - 1)
        return correct

    @property
    def phrase_done(self) -> bool:
        return not any(self.can_answer(player) for player in self.players)

    def finish_phrase(self) -> list[dict[str, object]]:
        """Charge unplayed notes as wrong and return one result row per player."""
        rows = []
        for player in self.players:
            phrase, answers = self.phrases[player], self.answers[player]
            correct = sum(expected == actual for expected, actual in zip(phrase, answers))
            wrong = len(answers) - correct
            missed = len(phrase) - len(answers)
            hp_before_misses = self.hp[player]
            # Unplayed notes cost HP, unless the boss already fell or the player is already out.
            penalty = 0 if self.boss_defeated else min(missed, hp_before_misses)
            self.hp[player] = hp_before_misses - penalty
            rows.append({
                "id": player,
                "notes": list(phrase),
                "answers": list(answers),
                "correct": correct,
                "wrong": wrong,
                "missed": missed,
                "damage": correct,
                "hp_lost": wrong + penalty,
            })
        return rows

    def reset(self) -> None:
        self.state = WAITING_FOR_PLAYERS
        self.round_number = 0
        self.players = []
        self.boss_hp = 0
        self.hp = {}
        self.scores = {}
        self.phrases = {}
        self.answers = {}
        self.rematch_votes.clear()
