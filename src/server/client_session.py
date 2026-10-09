"""Independent receive/send workers keep a slow peer out of the game lock."""
from __future__ import annotations
import queue
import socket
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any
from src.common.protocol import ProtocolError, receive_message, send_message
if TYPE_CHECKING:
    from .server import DupMeServer


class ClientSession:
    def __init__(self, server: 'DupMeServer', sock: socket.socket, address: tuple[str, int]):
        self.server, self.sock, self.address = server, sock, address
        self.player_id = uuid.uuid4().hex[:10]
        self.nickname: str | None = None
        self.connected_at = time.monotonic()
        self.last_received = self.connected_at
        self._closed = threading.Event()
        self._outgoing: queue.Queue[dict] = queue.Queue(maxsize=256)
        self.thread = threading.Thread(target=self._receive_loop, name=f'client-{self.player_id}', daemon=True)
        self.writer = threading.Thread(target=self._send_loop, name=f'sender-{self.player_id}', daemon=True)

    def start(self) -> None:
        self.writer.start()
        self.thread.start()

    def send(self, message: dict[str, Any]) -> bool:
        if self._closed.is_set():
            return False
        try:
            self._outgoing.put_nowait(message)
            return True
        except queue.Full:
            self.close()
            return False

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    def _send_loop(self) -> None:
        try:
            while not self._closed.is_set():
                try:
                    message = self._outgoing.get(timeout=0.2)
                except queue.Empty:
                    continue
                send_message(self.sock, message)
        except (OSError, ProtocolError):
            self.close()

    def _receive_loop(self) -> None:
        reason = 'Connection closed'
        try:
            while not self._closed.is_set():
                message = receive_message(self.sock)
                self.last_received = time.monotonic()
                self.server.handle_message(self, message)
        except (ProtocolError, ConnectionError, OSError) as exc:
            reason = str(exc) or reason
        finally:
            self.server.disconnect(self, reason)
