"""Small reusable presentation helpers for the client screens."""

from __future__ import annotations

from typing import Iterable


def score_text(scores: Iterable[dict]) -> str:
    rows = list(scores)
    return "    •    ".join(f"{row['nickname']}: {row['score']}" for row in rows) or "—"


def sequence_text(sequence: Iterable[str]) -> str:
    values = list(sequence)
    return "  →  ".join(value.title() for value in values) if values else "(none)"

