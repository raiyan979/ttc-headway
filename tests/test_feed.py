"""Feed fetch and parse. No network: HTTP is mocked, protobuf comes from fixtures."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import responses
from google.protobuf.message import DecodeError

from ttc_headway.config import Settings
from ttc_headway.feed import ResponseTooLarge, build_session, fetch_feed, parse_vehicles

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def test_parse_normal_fixture_yields_vehicles():
    raw = (FIXTURES / "normal.pb").read_bytes()
    header_ts, rows = parse_vehicles(raw, NOW)
    assert header_ts > 0
    assert len(rows) > 0
    row = rows[0]
    assert set(row) >= {"vehicle_id", "latitude", "longitude", "header_ts", "ingested_at"}
    assert row["ingested_at"] == NOW


def test_parse_malformed_fixture_raises():
    raw = (FIXTURES / "malformed.pb").read_bytes()
    with pytest.raises(DecodeError):
        parse_vehicles(raw, NOW)


@responses.activate
def test_fetch_returns_status_and_body():
    settings = Settings(feed_url="https://feed.test/vehicles")
    responses.add(responses.GET, settings.feed_url, body=b"\x01\x02\x03", status=200)
    status, body = fetch_feed(build_session(settings), settings)
    assert status == 200
    assert body == b"\x01\x02\x03"


@responses.activate
def test_fetch_enforces_size_cap():
    settings = Settings(feed_url="https://feed.test/vehicles", max_response_bytes=100)
    responses.add(responses.GET, settings.feed_url, body=b"x" * 1000, status=200)
    with pytest.raises(ResponseTooLarge):
        fetch_feed(build_session(settings), settings)
