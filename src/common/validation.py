"""Validation shared by the network-facing components."""

from __future__ import annotations

from .config import COLOR_NAMES, MAX_NICKNAME_LENGTH


def validate_nickname(value: object) -> tuple[bool, str]:
    if not isinstance(value, str):
        return False, "Nickname must be text."
    nickname = value.strip()
    if not nickname:
        return False, "Enter a nickname."
    if len(nickname) > MAX_NICKNAME_LENGTH:
        return False, f"Nickname can contain at most {MAX_NICKNAME_LENGTH} characters."
    if not all(character.isprintable() for character in nickname):
        return False, "Nickname contains unsupported characters."
    return True, nickname


def validate_color(value: object) -> bool:
    return isinstance(value, str) and value in COLOR_NAMES

