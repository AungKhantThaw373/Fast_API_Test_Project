"""Opaque keyset cursors for list endpoints.

Cursors are base64url JSON tuples of the ordering columns. They stay stable
while rows change, unlike offsets, and they serialize the exact values the
database compared so a page boundary cannot skip or repeat a row.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def clamp_limit(
    limit: int | None, *, default: int = DEFAULT_PAGE_SIZE, maximum: int = MAX_PAGE_SIZE
) -> int:
    if limit is None:
        return default
    return max(1, min(limit, maximum))


def encode_cursor(values: Sequence[Any]) -> str:
    serialized = [
        value.isoformat() if isinstance(value, datetime) else str(value) for value in values
    ]
    payload = json.dumps(serialized, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("ascii")).decode("ascii").rstrip("=")


def _invalid() -> HTTPException:
    return HTTPException(status_code=400, detail="Invalid pagination cursor.")


def decode_cursor(cursor: str, parsers: Sequence[Callable[[str], Any]]) -> list[Any]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise _invalid() from None
    if not isinstance(raw, list) or len(raw) != len(parsers):
        raise _invalid()
    try:
        return [parser(value) for parser, value in zip(parsers, raw, strict=True)]
    except (TypeError, ValueError):
        raise _invalid() from None


def keyset_predicate(
    columns: Sequence[Any], values: Sequence[Any], *, descending: bool
):
    """Lexicographic ``row > cursor`` (or ``<`` when descending), row-value style."""
    clauses = []
    for index, column in enumerate(columns):
        equalities = [columns[i] == values[i] for i in range(index)]
        comparison = column < values[index] if descending else column > values[index]
        clauses.append(and_(*equalities, comparison))
    return or_(*clauses)


def cursor_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def cursor_uuid(value: str) -> UUID:
    return UUID(value)


def cursor_text(value: str) -> str:
    return str(value)
