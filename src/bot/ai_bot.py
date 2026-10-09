"""Adaptive opponent using exactly the human client's TCP connection path."""
from __future__ import annotations
import argparse
import queue
import random
import threading
from typing import Any, Callable
from src.bot.difficulty_model import DifficultyModel
from src.client.network_client import NetworkClient
from src.common import message_types as mt
from src.common.config import COLOR_NAMES, SERVER_HOST, SERVER_PORT
from src.common.networking import validate_endpoint
from src.common.validation import validate_nickname


class AdaptiveBot:
    def __init__(self, nickname: str, host: str, port: int, difficulty: str,
                 log: Callable[[str], None] = print):
        self.nickname, self.host, self.port = nickname, host, port
        self.model = DifficultyModel(level=difficulty)
        self.events: queue.Queue[dict] = queue.Queue()
        self.network = NetworkClient(self.events, host, port)
        self.player_id: str | None = None
        self.observed_patterns: dict[int, list[str]] = {}
        self.running = True
        self._cancel = threading.Event()
        self._log = log
        self.error: str | None = None

    def connect_and_run(self) -> None:
        self._log(f'Connecting {self.nickname} to {self.host}:{self.port}...')
        self.network.connect_async(self.nickname)
        try:
            while self.running:
                try:
                    message = self.events.get(timeout=0.2)
                except queue.Empty:
                    continue
                if message.get('type') == 'network_error':
                    self.error = message['message']
                    self._log(self.error)
                    break
                self._handle(message)
        finally:
            self.close()

    def close(self) -> None:
        self.running = False
        self._cancel.set()
        self.network.close()

    def _new_phase(self) -> threading.Event:
        self._cancel.set()
        self._cancel = threading.Event()
        return self._cancel

    def _handle(self, message: dict[str, Any]) -> None:
        kind = message.get('type')
        if kind == mt.WELCOME:
            self.player_id = message['player_id']
            self._log(f"Joined as {message['nickname']} ({self.model.explanation()})")
        elif kind == mt.ROUND_START:
            cancel = self._new_phase()
            round_number, phase, role = int(message['round']), message['phase'], message['role']
            self._log(f'Round {round_number}: {phase}; bot role={role}')
            if phase == 'create':
                self.observed_patterns[round_number] = []
            target = self._create_pattern if phase == 'create' and role == 'creator' else (
                self._repeat_pattern if phase == 'repeat' and role == 'repeater' else None)
            if target:
                threading.Thread(target=target, args=(round_number, cancel, message['turn_id']), daemon=True).start()
        elif kind == mt.PATTERN_UPDATE:
            self.observed_patterns.setdefault(int(message['round']), []).append(message['color'])
        elif kind == mt.ROUND_RESULT:
            self._new_phase()
            if message.get('repeater_id') != self.player_id:
                self.model.observe_human_round(list(message.get('pattern', [])), list(message.get('answers', [])))
                self._log(f'AI analysis: {self.model.explanation()}')
        elif kind == mt.MATCH_RESULT:
            cancel = self._new_phase()
            if message.get('ended_early'):
                # A forfeit or host stop says nothing about how well the human played.
                self._log(f"Match ended early: {message.get('reason')}")
            else:
                level = self.model.observe_match(str(message.get('result', 'draw')))
                self._log(f"Match result: {message.get('result')}; next difficulty={level}")
            threading.Thread(target=self._vote_rematch, args=(cancel,), daemon=True).start()
        elif kind in (mt.GAME_RESET, mt.MATCH_START):
            self._new_phase()
            self.observed_patterns.clear()
        elif kind == mt.ERROR:
            self._log(f"Server: {message.get('message')}")

    def _create_pattern(self, round_number: int, cancel: threading.Event, turn_id: str) -> None:
        low, high = self.model.pattern_length_range()
        palette = random.sample(list(COLOR_NAMES), 3) if self.model.level == 'easy' else list(COLOR_NAMES)
        sequence = [random.choice(palette) for _ in range(random.randint(low, high))]
        if cancel.wait(0.5):
            return
        for color in sequence:
            if cancel.is_set() or not self.running:
                return
            self.network.send({'type': mt.PATTERN_STEP, 'color': color, 'turn_id': turn_id})
            if cancel.wait(self.model.press_delay()):
                return

    def _repeat_pattern(self, round_number: int, cancel: threading.Event, turn_id: str) -> None:
        pattern = list(self.observed_patterns.get(round_number, []))
        accuracy = random.uniform(*self.model.accuracy_range())
        if cancel.wait(0.6):
            return
        for expected in pattern:
            if cancel.is_set() or not self.running:
                return
            answer = expected if random.random() <= accuracy else random.choice([c for c in COLOR_NAMES if c != expected])
            self.network.send({'type': mt.REPEAT_STEP, 'color': answer, 'turn_id': turn_id})
            if cancel.wait(self.model.press_delay()):
                return

    def _vote_rematch(self, cancel: threading.Event) -> None:
        if not cancel.wait(2) and self.running:
            self.network.send({'type': mt.REMATCH_VOTE})


def main() -> int:
    parser = argparse.ArgumentParser(description='Adaptive networked opponent for Dup Me')
    parser.add_argument('--host', default=SERVER_HOST)
    parser.add_argument('--port', type=int, default=SERVER_PORT)
    parser.add_argument('--nickname', default='DupBot')
    parser.add_argument('--difficulty', choices=('easy', 'medium', 'hard'), default='medium')
    args = parser.parse_args()
    try:
        host, port = validate_endpoint(args.host, args.port)
        valid, nickname = validate_nickname(args.nickname)
        if not valid:
            raise ValueError(nickname)
    except ValueError as exc:
        parser.error(str(exc))
    bot = AdaptiveBot(nickname, host, port, args.difficulty)
    try:
        bot.connect_and_run()
    except KeyboardInterrupt:
        pass
    finally:
        bot.close()
    return 1 if bot.error else 0


if __name__ == '__main__':
    raise SystemExit(main())
