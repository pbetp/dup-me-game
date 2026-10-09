"""Cancellable TCP client; no socket operation runs on the Tkinter thread."""
from __future__ import annotations
import queue
import socket
import threading
import time
from typing import Any
from src.common import message_types as mt
from src.common.config import APP_VERSION, HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT, SERVER_HOST, SERVER_PORT
from src.common.networking import connection_error, validate_endpoint
from src.common.protocol import ProtocolError, receive_message, send_message


class NetworkClient:
    def __init__(self, event_queue: queue.Queue[dict[str, Any]], host: str = SERVER_HOST,
                 port: int = SERVER_PORT) -> None:
        self.events = event_queue
        self.host, self.port = validate_endpoint(host, port)
        self.sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._closing = threading.Event()
        self._started = False
        self._last_received = time.monotonic()
        self._outgoing: queue.Queue[dict | None] = queue.Queue(maxsize=128)

    def connect_async(self, nickname: str) -> None:
        with self._lock:
            if self._started or self._closing.is_set():
                return
            self._started = True
        threading.Thread(target=self._connect, args=(nickname,), name='client-connect', daemon=True).start()

    def _connect(self, nickname: str) -> None:
        sock = None
        try:
            sock = socket.create_connection((self.host, self.port), timeout=5)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self._lock:
                if self._closing.is_set():
                    sock.close()
                    return
                self.sock = sock
            send_message(sock, {'type': mt.JOIN, 'nickname': nickname, 'version': APP_VERSION})
            welcome = receive_message(sock)
            if welcome.get('type') == mt.ERROR:
                raise ProtocolError(str(welcome.get('message', 'Join rejected.')))
            if welcome.get('type') != mt.WELCOME or welcome.get('version') != APP_VERSION:
                raise ProtocolError('Server version differs. Use the same updated folder on both computers.')
            sock.settimeout(None)
            if self._closing.is_set():
                return
            self._last_received = time.monotonic()
            self.events.put(welcome)
            threading.Thread(target=self._send_loop, args=(sock,), name='client-sender', daemon=True).start()
            threading.Thread(target=self._heartbeat_loop, name="client-heartbeat", daemon=True).start()
            self._receive_loop(sock)
        except (OSError, ProtocolError, ValueError) as exc:
            self._fail(connection_error(self.host, self.port, exc))
        finally:
            if sock is not None:
                sock.close()
            self.close()

    def send(self, message: dict[str, Any]) -> bool:
        if self.sock is None or self._closing.is_set():
            return False
        try:
            self._outgoing.put_nowait(message)
            return True
        except queue.Full:
            self._fail('Connection is too slow. Reconnect to the server.')
            return False

    def _send_loop(self, sock: socket.socket) -> None:
        try:
            while not self._closing.is_set():
                try:
                    message = self._outgoing.get(timeout=0.5)
                except queue.Empty:
                    continue
                if message is None:
                    return
                send_message(sock, message)
        except (OSError, ProtocolError) as exc:
            self._fail(connection_error(self.host, self.port, exc))

    def _receive_loop(self, sock: socket.socket) -> None:
        while not self._closing.is_set():
            message = receive_message(sock)
            self._last_received = time.monotonic()
            if not self._closing.is_set():
                self.events.put(message)

    def _heartbeat_loop(self) -> None:
        while not self._closing.wait(HEARTBEAT_INTERVAL):
            if time.monotonic() - self._last_received > HEARTBEAT_TIMEOUT:
                self._fail("The server stopped responding. Reconnect to the same network, then find the host again.")
                return
            if not self.send({"type": mt.PING}):
                return

    def _fail(self, message: str) -> None:
        if not self._closing.is_set():
            self.events.put({'type': 'network_error', 'message': message})
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._closing.is_set():
                return
            self._closing.set()
            sock, self.sock = self.sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
