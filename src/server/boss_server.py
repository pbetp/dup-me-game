"""Co-op boss fight server: two players team up against THE DISSONANT.

Reuses DupMeServer's sockets, timer loop, joining, disconnects, reset and
dashboard. The controller loop treats the boss's "show" phase like a creation
phase and the players' answers like a repeat phase, so only the phase
handlers below differ from a 1v1 match.
"""

from __future__ import annotations

import time
import uuid

from src.common import message_types as mt
from src.common.config import BOSS_NAME, BOSS_NOTE_GAP, BOSS_RESULT_SECONDS
from src.common.validation import validate_color

from .boss_engine import BossEngine
from .client_session import ClientSession
from .game_engine import MATCH_RESULTS, WAITING_FOR_PLAYERS, WAITING_FOR_REMATCH
from .player_manager import registered_players
from .server import DupMeServer


def show_seconds(length: int) -> float:
    """Time for the boss to play a phrase, plus a breath before and after."""
    return 1.0 + length * BOSS_NOTE_GAP + 1.0


def repeat_seconds(length: int) -> int:
    return 6 + round(length * 1.5)


class BossFightServer(DupMeServer):
    mode = "boss"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.game = BossEngine(total_rounds=self.game.total_rounds)

    # ---- match flow ----

    def _start_match_if_possible_locked(self, preferred_creator: str | None = None,
                                      requested_by: str | None = None) -> bool:
        if self.game.state != WAITING_FOR_PLAYERS:
            return False
        available = registered_players(self.sessions.values())
        if len(available) < 2:
            return False
        if not self._lobby_start_allowed_locked(requested_by):
            return False
        player_ids = [session.player_id for session in available[:2]]
        self.game.begin_match(player_ids)
        self._announce_match_locked()
        self._broadcast_player_list_locked()
        return True

    def _announce_match_locked(self) -> None:
        self.deadline = None
        self.phase_closed = False
        self.pending_transition = None
        self._send_to_active({
            "type": mt.MATCH_START,
            "mode": self.mode,
            "players": self._score_rows(),
            "boss_name": BOSS_NAME,
            "boss_hp": self.game.boss_hp,
            "boss_max_hp": self.game.boss_max_hp,
            "total_rounds": self.game.total_rounds,
        })
        self._log(f"Boss fight started: {self._name(self.game.players[0])} + "
                  f"{self._name(self.game.players[1])} vs {BOSS_NAME}")
        self._start_creation_locked(1, already_initialized=True)

    def _start_creation_locked(self, round_number: int, already_initialized: bool = False) -> None:
        """The boss plays this phrase's melodies; each player hears only their own."""
        if not already_initialized:
            self.game.begin_phrase(round_number)
        length = max(len(notes) for notes in self.game.phrases.values())
        self.phase_closed = False
        self.deadline = time.monotonic() + show_seconds(length)
        self.last_timer_value = None
        self._send_phrase_locked("show", show_seconds(length))
        self._log(f"Phrase {round_number}: {BOSS_NAME} plays {length} notes")
        self._publish_snapshot()

    def _finish_creation_locked(self) -> None:
        if self.phase_closed:
            return
        self.game.begin_repeat()
        length = max(len(notes) for notes in self.game.phrases.values())
        self.deadline = time.monotonic() + repeat_seconds(length)
        self.last_timer_value = None
        self._send_phrase_locked("repeat", repeat_seconds(length))
        self._publish_snapshot()

    def _send_phrase_locked(self, phase: str, duration: float) -> None:
        self.turn_id = uuid.uuid4().hex
        for player_id in self.game.players:
            self._send_to_id(player_id, {
                "type": mt.BOSS_PHRASE,
                "turn_id": self.turn_id,
                "phase": phase,
                "phrase": self.game.round_number,
                "duration": round(duration, 2),
                "note_gap": BOSS_NOTE_GAP,
                # The melody is shown only while the boss plays it, and only to its own player.
                "notes": list(self.game.phrases[player_id]) if phase == "show" else [],
                "lengths": {pid: len(notes) for pid, notes in self.game.phrases.items()},
                "boss_hp": self.game.boss_hp,
                "boss_max_hp": self.game.boss_max_hp,
                "players": self._score_rows(),
            })

    def _pattern_step_locked(self, session: ClientSession, color: object) -> None:
        self._error(session, "Listen to the boss first, then repeat your phrase.")

    def _repeat_step_locked(self, session: ClientSession, color: object) -> None:
        if not self.game.is_repeating or self.phase_closed:
            self._error(session, "Wait for the boss to finish playing.")
            return
        if self.deadline is None or time.monotonic() >= self.deadline:
            self._error(session, "The repeat timer has expired.")
            return
        if not validate_color(color):
            self._error(session, "Unknown piano note.")
            return
        if not self.game.can_answer(session.player_id):
            self._error(session, "Your phrase is complete. Wait for your ally.")
            return
        assert isinstance(color, str)
        index = len(self.game.answers[session.player_id])
        correct = self.game.add_answer(session.player_id, color)
        self._send_to_active({
            "type": mt.BOSS_FEEDBACK,
            "player_id": session.player_id,
            "index": index,
            "color": color,
            "correct": correct,
            "boss_hp": self.game.boss_hp,
            "players": self._score_rows(),
        })
        if self.game.phrase_done:
            self._finish_repeat_locked()

    def _finish_repeat_locked(self) -> None:
        if self.phase_closed:
            return
        self.phase_closed = True
        self.deadline = None
        self.last_timer_value = None
        rows = self.game.finish_phrase()
        for row in rows:
            row["nickname"] = self._name(str(row["id"]))
        team_damage = sum(int(row["damage"]) for row in rows)
        self._send_to_active({
            "type": mt.BOSS_RESULT,
            "phrase": self.game.round_number,
            "results": rows,
            "team_damage": team_damage,
            "boss_hp": self.game.boss_hp,
            "boss_max_hp": self.game.boss_max_hp,
            "players": self._score_rows(),
        })
        self._log(f"Phrase {self.game.round_number}: team dealt {team_damage} damage, "
                  f"{BOSS_NAME} has {self.game.boss_hp} HP")
        over = self.game.boss_defeated or self.game.team_defeated
        self.pending_transition = (time.monotonic() + BOSS_RESULT_SECONDS,
                                   "match_result" if over else "next_round")
        self._publish_snapshot()

    def _finish_match_locked(self, forfeited_by: str | None = None, reason: str = "") -> None:
        self.deadline = None
        self.phase_closed = True
        self.last_timer_value = None
        self.pending_transition = None
        self.game.state = MATCH_RESULTS
        won = self.game.boss_defeated and forfeited_by is None
        self.previous_winner = None
        for player_id in self.game.players:
            message = reason
            if forfeited_by is not None:
                message = ("You left the fight." if player_id == forfeited_by
                           else f"{self._name(forfeited_by)} left the fight.")
            elif not message:
                message = (f"Boss defeated in {self.game.round_number} phrases." if won
                           else f"The boss survived with {self.game.boss_hp} HP.")
            self._send_to_id(player_id, {
                "type": mt.MATCH_RESULT,
                "mode": self.mode,
                "result": "win" if won else "loss",
                "winner_id": None,
                "scores": self._score_rows(),
                "reason": message,
                "ended_early": forfeited_by is not None or bool(reason),
                "boss_hp": self.game.boss_hp,
                "boss_max_hp": self.game.boss_max_hp,
                "phrases": self.game.round_number,
            })
        self.game.state = WAITING_FOR_REMATCH
        self._log(f"Boss fight complete: {'victory' if won else 'defeat'}")
        self._publish_snapshot()

    def _rematch_vote_locked(self, session: ClientSession) -> None:
        if self.game.state != WAITING_FOR_REMATCH or session.player_id not in self.game.players:
            self._error(session, "A rematch vote is not allowed now.")
            return
        self.game.rematch_votes.add(session.player_id)
        self._send_to_active({"type": "rematch_status", "votes": len(self.game.rematch_votes), "needed": 2})
        self._log(f"{session.nickname} voted for a rematch")
        if self.game.rematch_votes == set(self.game.players):
            current_players = list(self.game.players)
            self.game.reset()
            self.game.begin_match(current_players)
            self._announce_match_locked()

    # ---- presentation ----

    def _score_rows(self) -> list[dict[str, object]]:
        return [
            {
                "id": player_id,
                "nickname": self._name(player_id),
                "score": self.game.scores.get(player_id, 0),
                "hp": self.game.hp.get(player_id, 0),
                "max_hp": self.game.player_max_hp,
            }
            for player_id in self.game.players
        ]

    def snapshot(self) -> dict:
        with self.lock:
            snapshot = super().snapshot()
            snapshot.update(
                boss_hp=self.game.boss_hp,
                boss_max_hp=self.game.boss_max_hp,
                hp={self._name(player_id): hp for player_id, hp in self.game.hp.items()},
            )
            return snapshot
