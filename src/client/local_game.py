"""Own the optional server and bot for one launcher window."""
from __future__ import annotations
import threading
from src.bot.ai_bot import AdaptiveBot
from src.common.config import DEFAULT_ROUNDS, SERVER_PORT
from src.server.server import DupMeServer


class LocalGame:
    def __init__(self):
        self.server: DupMeServer | None = None
        self.bot: AdaptiveBot | None = None
        self.bot_thread: threading.Thread | None = None

    def start(self, solo: bool = False, port: int = SERVER_PORT, total_rounds: int = DEFAULT_ROUNDS) -> int:
        self.close()
        # Solo never occupies the shared LAN port or accepts remote players.
        server = DupMeServer(host='127.0.0.1' if solo else '0.0.0.0', port=0 if solo else port, total_rounds=total_rounds)
        server.start()
        self.server = server
        return server.port

    def start_bot(self, human_nickname: str, difficulty: str = 'medium') -> None:
        if self.server is None or self.bot is not None:
            return
        name = 'DupBot' if human_nickname.casefold() != 'dupbot' else 'DupBot AI'
        self.bot = AdaptiveBot(name, '127.0.0.1', self.server.port, difficulty)
        self.bot_thread = threading.Thread(target=self.bot.connect_and_run, name='local-bot', daemon=True)
        self.bot_thread.start()

    def close(self) -> None:
        if self.bot is not None:
            self.bot.close()
            self.bot = None
        if self.server is not None:
            self.server.stop()
            self.server = None
        if self.bot_thread is not None:
            self.bot_thread.join(timeout=0.5)
            self.bot_thread = None
