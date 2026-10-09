"""Helpers for presenting connected players."""

from __future__ import annotations

from typing import Iterable

from .client_session import ClientSession


def registered_players(sessions: Iterable[ClientSession]) -> list[ClientSession]:
    return [session for session in sessions if session.nickname is not None]


def public_player(session: ClientSession, active_ids: set[str]) -> dict[str, object]:
    return {
        "id": session.player_id,
        "nickname": session.nickname,
        "address": session.address[0],
        "in_match": session.player_id in active_ids,
    }

