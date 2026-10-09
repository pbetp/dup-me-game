"""Threaded authoritative game server."""

from __future__ import annotations

import math
import queue
import random
import socket
import threading
import time
import uuid
from typing import Any

from src.common import message_types as mt
from src.common.config import (
    APP_VERSION,
    COLOR_NAMES,
    DEFAULT_ROUNDS,
    DISCOVERY_PORT,
    HEARTBEAT_TIMEOUT,
    CREATE_SECONDS,
    MAX_PATTERN_STEPS,
    PHASE_RESULT_SECONDS,
    REPEAT_SECONDS,
    SERVER_BIND_HOST,
    SERVER_PORT,
)
from src.common.validation import validate_color, validate_nickname
from src.common.discovery import DiscoveryResponder

from .client_session import ClientSession
from .game_engine import (
    MATCH_RESULTS,
    WAITING_FOR_PLAYERS,
    WAITING_FOR_REMATCH,
    GameEngine,
)
from .player_manager import public_player, registered_players


class DupMeServer:
    def __init__(
        self,
        event_queue: queue.Queue[dict[str, Any]] | None = None,
        host: str = SERVER_BIND_HOST,
        port: int = SERVER_PORT,
        total_rounds: int = DEFAULT_ROUNDS,
        advertise: bool | None = None,
        discovery_port: int = DISCOVERY_PORT,
        name: str | None = None,
    ) -> None:
        self.advertise = (host == "0.0.0.0") if advertise is None else advertise
        self.discovery_port = discovery_port
        self.discovery = None
        self.discovery_status = "Private local game"
        self.server_id = uuid.uuid4().hex
        self.name = (name or socket.gethostname())[:60]
        self.host = host
        self.port = port
        self.event_queue = event_queue
        self.game = GameEngine(total_rounds=total_rounds)
        self.sessions: dict[str, ClientSession] = {}
        self.lock = threading.RLock()
        self.running = threading.Event()
        self.listener: socket.socket | None = None
        self.deadline: float | None = None
        self.phase_closed = False
        self.last_timer_value: int | None = None
        self.pending_transition: tuple[float, str] | None = None
        self.previous_winner: str | None = None
        self.turn_id = ""
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self.running.is_set():
            raise RuntimeError("This server is already running.")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Windows needs exclusive ownership; POSIX reuse permits a clean restart.
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self.host, self.port))
            listener.listen(16)
            listener.settimeout(0.2)
        except OSError:
            listener.close()
            raise
        self.port = listener.getsockname()[1]
        self.listener = listener
        self.running.set()
        self._threads = [
            threading.Thread(target=self._accept_loop, args=(listener,), name="listener", daemon=True),
            threading.Thread(target=self._controller_loop, name="controller", daemon=True),
        ]
        for thread in self._threads:
            thread.start()
        if self.advertise:
            self.discovery = DiscoveryResponder(self.discovery_info, self.discovery_port)
            try:
                self.discovery.start()
                self.discovery_status = f"Nearby discovery on UDP {self.discovery.port}"
            except OSError:
                self.discovery = None
                self.discovery_status = "Discovery unavailable. Use Save Connection File."
        self._log(f"Listening on {self.host}:{self.port}")
        self._publish_snapshot()

    def stop(self) -> None:
        self.running.clear()
        if self.discovery:
            self.discovery.close()
            self.discovery = None
        listener, self.listener = self.listener, None
        if listener is not None:
            try:
                listener.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            listener.close()
        with self.lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()
            self.game.reset()
            self.deadline = self.pending_transition = None
            self.phase_closed = False
            self.previous_winner = None
        for session in sessions:
            session.close()
        for thread in self._threads + [t for s in sessions for t in (s.thread, s.writer)]:
            if thread is not threading.current_thread() and thread.ident is not None:
                thread.join(timeout=0.5)
        self._threads.clear()
        self._log("Server stopped")

    def _accept_loop(self, listener: socket.socket) -> None:
        while self.running.is_set():
            try:
                sock, address = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self.lock:
                if not self.running.is_set() or len(self.sessions) >= 16:
                    sock.close()
                    continue
                session = ClientSession(self, sock, address)
                self.sessions[session.player_id] = session
                session.start()
            self._log(f"Connection from {address[0]} (awaiting nickname)")
            self._publish_snapshot()

    def _controller_loop(self) -> None:
        while self.running.is_set():
            with self.lock:
                now = time.monotonic()
                for session in list(self.sessions.values()):
                    if session.nickname is None and now - session.connected_at > 10:
                        self.disconnect(session, "Join timed out")
                    elif session.nickname is not None and now - session.last_received > HEARTBEAT_TIMEOUT:
                        self.disconnect(session, "Connection heartbeat timed out")
                if self.deadline is not None and not self.phase_closed:
                    remaining = max(0, math.ceil(self.deadline - now))
                    if remaining != self.last_timer_value:
                        self.last_timer_value = remaining
                        self._send_to_active({"type": mt.TIMER_UPDATE, "remaining": remaining})
                        self._publish_snapshot()
                    if now >= self.deadline:
                        if self.game.is_creating:
                            self._finish_creation_locked()
                        elif self.game.is_repeating:
                            self._finish_repeat_locked()
                if self.pending_transition and now >= self.pending_transition[0]:
                    _when, transition = self.pending_transition
                    self.pending_transition = None
                    if transition == "next_round":
                        self._start_creation_locked(self.game.round_number + 1)
                    elif transition == "match_result":
                        self._finish_match_locked()
                    elif transition == "auto_start":
                        self._start_match_if_possible_locked()
            time.sleep(0.1)

    def handle_message(self, session: ClientSession, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        with self.lock:
            if session.player_id not in self.sessions or not self.running.is_set():
                return
            if message_type == mt.PING:
                session.send({"type": mt.PONG, "app": "Dup Me", "version": APP_VERSION})
                return
            if session.nickname is None:
                if message_type != mt.JOIN:
                    self._error(session, "Join with a nickname first.")
                    return
                if message.get("version") != APP_VERSION:
                    self._error(session, "Version mismatch. Use the same updated folder on both computers.")
                    return
                self._join_locked(session, message.get("nickname"))
                return
            if message_type in (mt.PATTERN_STEP, mt.REPEAT_STEP) and message.get("turn_id") != self.turn_id:
                self._error(session, "That move belongs to an earlier turn.")
                return
            if message_type == mt.PATTERN_STEP:
                self._pattern_step_locked(session, message.get("color"))
            elif message_type == mt.REPEAT_STEP:
                self._repeat_step_locked(session, message.get("color"))
            elif message_type == mt.REMATCH_VOTE:
                self._rematch_vote_locked(session)
            elif message_type == mt.FORFEIT:
                self._forfeit_locked(session)
            elif message_type == mt.PONG:
                return
            else:
                self._error(session, f"Unknown or unavailable message type: {message_type}")

    def _join_locked(self, session: ClientSession, raw_nickname: object) -> None:
        valid, result = validate_nickname(raw_nickname)
        if not valid:
            self._error(session, result)
            return
        nickname = result
        duplicate = any(
            other.nickname and other.nickname.casefold() == nickname.casefold()
            for other in self.sessions.values()
            if other is not session
        )
        if duplicate:
            self._error(session, "That nickname is already connected.")
            return
        session.nickname = nickname
        session.send(
            {
                "type": mt.WELCOME,
                "player_id": session.player_id,
                "nickname": nickname,
                "version": APP_VERSION,
                "total_rounds": self.game.total_rounds,
            }
        )
        self._log(f"{nickname} joined from {session.address[0]}")
        self._broadcast_player_list_locked()
        self._start_match_if_possible_locked()

    def _start_match_if_possible_locked(self, preferred_creator: str | None = None) -> bool:
        if self.game.state != WAITING_FOR_PLAYERS:
            return False
        available = registered_players(self.sessions.values())
        if len(available) < 2:
            return False
        selected = available[:2]
        player_ids = [session.player_id for session in selected]
        creator = preferred_creator if preferred_creator in player_ids else random.choice(player_ids)
        self.game.begin_match(player_ids, creator)
        self.deadline = None
        self.phase_closed = False
        self.pending_transition = None
        self._send_to_active(
            {
                "type": mt.MATCH_START,
                "players": self._score_rows(),
                "first_creator_id": creator,
                "total_rounds": self.game.total_rounds,
            }
        )
        self._log(
            f"Match started: {self._name(player_ids[0])} vs {self._name(player_ids[1])}"
        )
        self._start_creation_locked(1, already_initialized=True)
        self._broadcast_player_list_locked()
        return True

    def _start_creation_locked(self, round_number: int, already_initialized: bool = False) -> None:
        if not already_initialized:
            self.game.begin_creation(round_number)
        self.phase_closed = False
        self.deadline = time.monotonic() + CREATE_SECONDS
        self.last_timer_value = None
        self._send_round_start_locked("create", CREATE_SECONDS)
        self._log(
            f"Round {round_number}: {self._name(self.game.creator)} creates the pattern"
        )
        self._publish_snapshot()

    def _pattern_step_locked(self, session: ClientSession, color: object) -> None:
        if not self.game.is_creating or self.phase_closed:
            self._error(session, "Pattern input is not allowed now.")
            return
        if session.player_id != self.game.creator:
            self._error(session, "Only the creator can add pattern steps.")
            return
        if self.deadline is None or time.monotonic() >= self.deadline:
            self._error(session, "The creation timer has expired.")
            return
        if not validate_color(color):
            self._error(session, "Unknown piano note.")
            return
        assert isinstance(color, str)
        if len(self.game.pattern) >= MAX_PATTERN_STEPS:
            self._error(session, "The pattern is full. Wait for the creation timer.")
            return
        self.game.add_pattern_step(color)
        self._send_to_active(
            {
                "type": mt.PATTERN_UPDATE,
                "color": color,
                "length": len(self.game.pattern),
                "round": self.game.round_number,
                "total_rounds": self.game.total_rounds,
            }
        )

    def _finish_creation_locked(self) -> None:
        if self.phase_closed:
            return
        self.phase_closed = True
        self.game.begin_repeat()
        self.phase_closed = False
        self.deadline = time.monotonic() + REPEAT_SECONDS
        self.last_timer_value = None
        self._send_round_start_locked("repeat", REPEAT_SECONDS)
        self._log(
            f"Round {self.game.round_number}: {self._name(self.game.repeater)} repeats "
            f"{len(self.game.pattern)} steps"
        )
        self._publish_snapshot()

    def _repeat_step_locked(self, session: ClientSession, color: object) -> None:
        if not self.game.is_repeating or self.phase_closed:
            self._error(session, "Repeat input is not allowed now.")
            return
        if session.player_id != self.game.repeater:
            self._error(session, "Only the repeater can answer.")
            return
        if self.deadline is None or time.monotonic() >= self.deadline:
            self._error(session, "The repeat timer has expired.")
            return
        if not validate_color(color):
            self._error(session, "Unknown piano note.")
            return
        assert isinstance(color, str)
        index = len(self.game.answers)
        correct = self.game.add_answer(color)
        self._send_to_active(
            {
                "type": mt.REPEAT_FEEDBACK,
                "index": index,
                "color": color,
                "correct": correct,
                "answered": len(self.game.answers),
                "total": len(self.game.pattern),
                "scores": self._score_rows(),
            }
        )
        if len(self.game.answers) >= len(self.game.pattern):
            self._finish_repeat_locked()

    def _finish_repeat_locked(self) -> None:
        if self.phase_closed:
            return
        self.phase_closed = True
        self.deadline = None
        self.last_timer_value = None
        self._send_to_active(
            {
                "type": mt.ROUND_RESULT,
                "round": self.game.round_number,
                "total_rounds": self.game.total_rounds,
                "pattern": list(self.game.pattern),
                "answers": list(self.game.answers),
                "points": self.game.round_points(),
                "repeater_id": self.game.repeater,
                "scores": self._score_rows(),
            }
        )
        self._log(
            f"Round {self.game.round_number} complete: "
            f"{self._name(self.game.repeater)} scored {self.game.round_points()}"
        )
        transition = "next_round" if self.game.round_number < self.game.total_rounds else "match_result"
        self.pending_transition = (time.monotonic() + PHASE_RESULT_SECONDS, transition)
        self._publish_snapshot()

    def _match_in_progress_locked(self) -> bool:
        return bool(self.game.players) and self.game.state not in (
            WAITING_FOR_PLAYERS, MATCH_RESULTS, WAITING_FOR_REMATCH)

    def _finish_match_locked(self, forfeited_by: str | None = None, reason: str = "") -> None:
        # Also used to end a match early, so stop any running timer or queued transition.
        self.deadline = None
        self.phase_closed = True
        self.last_timer_value = None
        self.pending_transition = None
        self.game.state = MATCH_RESULTS
        if forfeited_by is not None:
            winner = next(player for player in self.game.players if player != forfeited_by)
        else:
            winner = self.game.winner()
        self.previous_winner = winner
        for player_id in self.game.players:
            if winner is None:
                result = "draw"
            elif player_id == winner:
                result = "win"
            else:
                result = "loss"
            message = reason
            if forfeited_by is not None:
                message = ("You forfeited the match." if player_id == forfeited_by
                           else f"{self._name(forfeited_by)} forfeited the match.")
            self._send_to_id(
                player_id,
                {
                    "type": mt.MATCH_RESULT,
                    "result": result,
                    "winner_id": winner,
                    "scores": self._score_rows(),
                    "reason": message,
                    "ended_early": bool(message),
                },
            )
        self.game.state = WAITING_FOR_REMATCH
        winner_text = self._name(winner) if winner else "Draw"
        self._log(f"Match complete. Result: {winner_text}")
        self._publish_snapshot()

    def _forfeit_locked(self, session: ClientSession) -> None:
        if session.player_id not in self.game.players or not self._match_in_progress_locked():
            self._error(session, "There is no match in progress to leave.")
            return
        self._log(f"{session.nickname} forfeited the match")
        self._finish_match_locked(forfeited_by=session.player_id)

    def end_match(self, reason: str = "The host ended the match.") -> bool:
        """End the current match now; the winner is decided by the current scores."""
        with self.lock:
            if not self._match_in_progress_locked():
                return False
            self._log(reason)
            self._finish_match_locked(reason=reason)
            return True

    def _rematch_vote_locked(self, session: ClientSession) -> None:
        if self.game.state != WAITING_FOR_REMATCH or session.player_id not in self.game.players:
            self._error(session, "A rematch vote is not allowed now.")
            return
        self.game.rematch_votes.add(session.player_id)
        self._send_to_active(
            {
                "type": "rematch_status",
                "votes": len(self.game.rematch_votes),
                "needed": 2,
            }
        )
        self._log(f"{session.nickname} voted for a rematch")
        if self.game.rematch_votes == set(self.game.players):
            preferred = self.previous_winner
            current_players = list(self.game.players)
            self.game.reset()
            # Retain the same pair even if spectators are connected.
            creator = preferred if preferred in current_players else random.choice(current_players)
            self.game.begin_match(current_players, creator)
            self._send_to_active(
                {
                    "type": mt.MATCH_START,
                    "players": self._score_rows(),
                    "first_creator_id": creator,
                    "total_rounds": self.game.total_rounds,
                }
            )
            self._start_creation_locked(1, already_initialized=True)

    def reset_game(self, reason: str = "The server reset the game.") -> None:
        """Clear the match and scores, then restart at round 1 straight away if two players remain."""
        with self.lock:
            self.game.reset()
            self.deadline = None
            self.phase_closed = False
            self.last_timer_value = None
            self.pending_transition = None
            self.previous_winner = None
            self._broadcast({"type": mt.GAME_RESET, "reason": reason})
            self._broadcast_player_list_locked()
            self._log(reason)
            if not self._start_match_if_possible_locked():
                self.pending_transition = (time.monotonic() + 2.0, "auto_start")
            self._publish_snapshot()

    def disconnect(self, session: ClientSession, reason: str = "Disconnected") -> None:
        with self.lock:
            if self.sessions.pop(session.player_id, None) is None:
                return
            session.close()
            nickname = session.nickname or session.address[0]
            was_active = session.player_id in self.game.players
            self._log(f"{nickname} disconnected: {reason}")
            self._broadcast(
                {"type": mt.PLAYER_LEFT, "player_id": session.player_id, "nickname": nickname}
            )
            if was_active:
                self.game.reset()
                self.deadline = None
                self.phase_closed = False
                self.pending_transition = (time.monotonic() + 2.0, "auto_start")
                self._broadcast(
                    {
                        "type": mt.GAME_RESET,
                        "reason": f"{nickname} left. The match was cancelled.",
                    }
                )
            self._broadcast_player_list_locked()
            self._publish_snapshot()

    def _send_round_start_locked(self, phase: str, duration: int) -> None:
        self.turn_id = uuid.uuid4().hex
        for player_id in self.game.players:
            role = "creator" if player_id == self.game.creator else "repeater"
            self._send_to_id(
                player_id,
                {
                    "type": mt.ROUND_START,
                    "turn_id": self.turn_id,
                    "round": self.game.round_number,
                    "total_rounds": self.game.total_rounds,
                    "phase": phase,
                    "role": role,
                    "creator_id": self.game.creator,
                    "creator_name": self._name(self.game.creator),
                    "repeater_id": self.game.repeater,
                    "repeater_name": self._name(self.game.repeater),
                    "duration": duration,
                    "pattern_length": len(self.game.pattern),
                    "scores": self._score_rows(),
                },
            )

    def _broadcast_player_list_locked(self) -> None:
        active_ids = set(self.game.players)
        players = [public_player(session, active_ids) for session in registered_players(self.sessions.values())]
        self._broadcast({"type": mt.PLAYER_LIST, "players": players})
        self._publish_snapshot()

    def _score_rows(self) -> list[dict[str, object]]:
        return [
            {
                "id": player_id,
                "nickname": self._name(player_id),
                "score": self.game.scores.get(player_id, 0),
            }
            for player_id in self.game.players
        ]

    def _name(self, player_id: str | None) -> str:
        if player_id is None:
            return "—"
        session = self.sessions.get(player_id)
        return session.nickname if session and session.nickname else player_id

    def _send_to_id(self, player_id: str, message: dict[str, Any]) -> None:
        session = self.sessions.get(player_id)
        if session:
            session.send(message)

    def _send_to_active(self, message: dict[str, Any]) -> None:
        for player_id in list(self.game.players):
            self._send_to_id(player_id, message)

    def _broadcast(self, message: dict[str, Any]) -> None:
        for session in list(self.sessions.values()):
            if session.nickname is not None:
                session.send(message)

    @staticmethod
    def _error(session: ClientSession, message: str) -> None:
        session.send({"type": mt.ERROR, "message": message})

    def discovery_info(self) -> dict[str, Any]:
        with self.lock:
            return {"server_id": self.server_id, "name": self.name, "port": self.port,
                    "players": len(registered_players(self.sessions.values())),
                    "total_rounds": self.game.total_rounds}

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            players = [
                {
                    "nickname": session.nickname or "(joining)",
                    "address": session.address[0],
                    "id": session.player_id,
                }
                for session in self.sessions.values() if session.nickname is not None
            ]
            scores = {
                self._name(player_id): score for player_id, score in self.game.scores.items()
            }
            remaining = None
            if self.deadline is not None and not self.phase_closed:
                remaining = max(0, math.ceil(self.deadline - time.monotonic()))
            return {
                "type": "snapshot",
                "running": self.running.is_set(),
                "online_count": len(players),
                "connection_count": len(self.sessions),
                "players": players,
                "state": self.game.state,
                "round": self.game.round_number,
                "total_rounds": self.game.total_rounds,
                "creator": self._name(self.game.creator),
                "repeater": self._name(self.game.repeater),
                "scores": scores,
                "remaining": remaining,
            }

    def _publish_snapshot(self) -> None:
        if self.event_queue is not None:
            self.event_queue.put(self.snapshot())

    def _log(self, message: str) -> None:
        if self.event_queue is not None:
            self.event_queue.put({"type": "log", "message": message})


def serve_forever() -> None:
    server = DupMeServer()
    server.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    serve_forever()
