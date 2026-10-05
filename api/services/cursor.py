"""Opaque keyset cursors: base64url of the JSON pair `[created_at, id]`.

A cursor says where the previous page ended. It carries no tenant and grants nothing: every query that uses
it still runs under the caller's tenant and row-level security.
"""
import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

# Years near 1 and 9999 overflow when the driver converts to UTC. No real row is that old or that new.
MIN_YEAR = 1970
MAX_YEAR = 9000


class InvalidCursor(ValueError):
    """The cursor is not one `encode_cursor` made."""


def encode_key_cursor(created_at: datetime, key: str) -> str:
    """A cursor over `(created_at, key)` where the key is any text, such as a request id."""
    raw = json.dumps([created_at.isoformat(), key], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def encode_cursor(created_at: datetime, row_id: UUID) -> str:
    return encode_key_cursor(created_at, str(row_id))


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    created_at, row_id = decode_key_cursor(cursor)
    try:
        return created_at, UUID(row_id)
    except ValueError as exc:
        raise InvalidCursor("invalid cursor") from exc


def decode_key_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        stamp, row_id = json.loads(raw)
        if not isinstance(row_id, str):
            raise ValueError("id is not a string")
        created_at = datetime.fromisoformat(stamp)
        if created_at.tzinfo is None:
            raise ValueError("naive timestamp")
        if not MIN_YEAR <= created_at.year <= MAX_YEAR:
            raise ValueError("timestamp out of range")
        return created_at, row_id
    except (binascii.Error, ValueError, TypeError, AttributeError, OverflowError, UnicodeDecodeError) as exc:
        raise InvalidCursor("invalid cursor") from exc
