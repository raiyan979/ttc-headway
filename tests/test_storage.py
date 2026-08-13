"""Storage: raw framing round-trip, slot idempotency, service-date partitioning."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq

from ttc_headway.storage import (
    VEHICLE_SCHEMA,
    frame_messages,
    slot_bounds,
    unframe_messages,
    write_cycle,
)

TORONTO = ZoneInfo("America/Toronto")


def test_frame_unframe_roundtrip_including_empty_message():
    messages = [b"abc", b"", b"\x00\x01\x02\xff", b"x" * 1000]
    assert unframe_messages(frame_messages(messages)) == messages


def test_slot_bounds_floors_to_ten_minutes():
    start, end = slot_bounds(datetime(2026, 8, 14, 17, 16, 43, tzinfo=TORONTO))
    assert (start.hour, start.minute, start.second) == (17, 10, 0)
    assert (end.hour, end.minute) == (17, 20)


def test_slot_bounds_is_idempotent_within_a_slot():
    # A late run at :16 and an on-time run at :19 name the same slot -> overwrite.
    a, _ = slot_bounds(datetime(2026, 8, 14, 17, 16, tzinfo=TORONTO))
    b, _ = slot_bounds(datetime(2026, 8, 14, 17, 19, 59, tzinfo=TORONTO))
    assert a == b


def test_slot_bounds_crosses_midnight():
    start, end = slot_bounds(datetime(2026, 8, 14, 23, 55, tzinfo=TORONTO))
    assert (start.hour, start.minute) == (23, 50)
    assert (end.day, end.hour, end.minute) == (15, 0, 0)


def _row(vehicle_id: str) -> dict:
    return {name: None for name in VEHICLE_SCHEMA.names} | {
        "entity_id": vehicle_id,
        "vehicle_id": vehicle_id,
        "header_ts": 1,
        "ingested_at": datetime(2026, 8, 14, 6, 30, tzinfo=UTC),
    }


def test_write_cycle_partitions_on_service_date(tmp_path):
    # 02:30 Toronto belongs to the previous service day, not the calendar date.
    started = datetime(2026, 8, 14, 2, 30, tzinfo=TORONTO)
    rows = [_row("a"), _row("b")]
    parquet_path, pb_path = write_cycle(str(tmp_path), started, rows, [b"raw-bytes"])

    assert "dt=2026-08-13" in parquet_path.as_posix()
    assert "dt=2026-08-13" in pb_path.as_posix()
    assert pq.read_table(parquet_path).num_rows == 2
    # The .tmp siblings must not survive an atomic write.
    assert not list(tmp_path.rglob("*.tmp"))


def test_write_cycle_with_no_rows_still_writes_raw_insurance(tmp_path):
    # Fetches succeeded but every decode failed: the raw .pb.gz must still be
    # written (it is the reprocessing insurance), with a valid 0-row Parquet.
    started = datetime(2026, 8, 14, 17, 15, tzinfo=TORONTO)
    parquet_path, pb_path = write_cycle(str(tmp_path), started, [], [b"raw-1", b"raw-2"])
    assert pb_path.exists()
    assert pq.read_table(parquet_path).num_rows == 0
