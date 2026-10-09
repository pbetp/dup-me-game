"""Length-prefixed JSON protocol used by server, clients, and bot."""

from __future__ import annotations

import json
import socket
import struct
from typing import Any

from .config import MAX_MESSAGE_BYTES


class ProtocolError(Exception):
    """Raised when a peer sends malformed or unsafe data."""


def encode_message(message: dict[str, Any]) -> bytes:
    if not isinstance(message, dict):
        raise ProtocolError("Messages must be JSON objects")
    try:
        payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("Message is not JSON serializable") from exc
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Message is too large")
    return struct.pack("!I", len(payload)) + payload


def send_message(sock: socket.socket, message: dict[str, Any]) -> None:
    sock.sendall(encode_message(message))


def _receive_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Peer disconnected")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def receive_message(sock: socket.socket) -> dict[str, Any]:
    header = _receive_exact(sock, 4)
    (size,) = struct.unpack("!I", header)
    if size <= 0 or size > MAX_MESSAGE_BYTES:
        raise ProtocolError("Invalid message length")
    payload = _receive_exact(sock, size)
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ProtocolError("Malformed JSON") from exc
    if not isinstance(message, dict):
        raise ProtocolError("Message must be a JSON object")
    if not isinstance(message.get("type"), str):
        raise ProtocolError("Message has no valid type")
    return message

