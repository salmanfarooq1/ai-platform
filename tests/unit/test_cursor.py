"""Cursor round-trips (property test) and rejection of anything that is not a cursor."""
import base64
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from api.services.cursor import InvalidCursor, decode_cursor, encode_cursor

pytestmark = pytest.mark.unit

aware_datetimes = st.datetimes(
    min_value=datetime(1970, 1, 2), max_value=datetime(9000, 1, 1),
    timezones=st.one_of(st.just(timezone.utc), st.integers(-12, 14).map(lambda h: timezone(timedelta(hours=h)))),
)


@given(created_at=aware_datetimes, row_id=st.uuids())
def test_a_cursor_round_trips_exactly(created_at, row_id):
    cursor = encode_cursor(created_at, row_id)
    assert decode_cursor(cursor) == (created_at, row_id)
    assert cursor.isascii() and "=" not in cursor and "/" not in cursor and "+" not in cursor


@given(created_at=aware_datetimes, row_id=st.uuids())
def test_a_cursor_is_opaque_and_carries_no_tenant(created_at, row_id):
    raw = base64.urlsafe_b64decode(encode_cursor(created_at, row_id) + "==")
    assert len(json.loads(raw)) == 2


@given(text=st.text(max_size=80))
def test_arbitrary_text_is_rejected_or_decodes_to_a_valid_pair(text):
    try:
        stamp, row_id = decode_cursor(text)
    except InvalidCursor:
        return
    assert stamp.tzinfo is not None and isinstance(row_id, UUID)


@pytest.mark.parametrize("bad", [
    "", "not-a-cursor", "!!!!", base64.urlsafe_b64encode(b"[]").decode(),
    base64.urlsafe_b64encode(b'["2026-01-01T00:00:00","00000000-0000-0000-0000-000000000001"]').decode(),  # naive time
    base64.urlsafe_b64encode(b'["2026-01-01T00:00:00+00:00","nope"]').decode(),
    base64.urlsafe_b64encode(b'{"a": 1}').decode(),
    base64.urlsafe_b64encode(b'[1, 2]').decode(),
])
def test_bad_cursors_raise_invalid_cursor(bad):
    with pytest.raises(InvalidCursor):
        decode_cursor(bad)


@pytest.mark.parametrize("bad", [
    base64.urlsafe_b64encode(b'["2026-01-01T00:00:00+00:00", 5]').decode(),  # numeric id: UUID(5) raised AttributeError
    base64.urlsafe_b64encode(b'["2026-01-01T00:00:00+00:00", null]').decode(),
    base64.urlsafe_b64encode(b'["2026-01-01T00:00:00+00:00", ["x"]]').decode(),
    base64.urlsafe_b64encode(b'["0001-01-01T00:00:00+00:00","00000000-0000-0000-0000-000000000001"]').decode(),
    base64.urlsafe_b64encode(b'["0001-01-01T00:00:00+14:00","00000000-0000-0000-0000-000000000001"]').decode(),
    base64.urlsafe_b64encode(b'["9999-12-31T23:59:59-12:00","00000000-0000-0000-0000-000000000001"]').decode(),
    base64.urlsafe_b64encode(b'["9999-12-31T23:59:59.999999+00:00","00000000-0000-0000-0000-000000000001"]').decode(),
])
def test_crafted_cursors_raise_invalid_cursor_not_other_errors(bad):
    with pytest.raises(InvalidCursor):
        decode_cursor(bad)
