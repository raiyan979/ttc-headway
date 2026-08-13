"""Write one collection cycle to disk: a decoded Parquet file and a raw-bytes
insurance file, both idempotently.

Raw realtime data is not re-downloadable. If the decoder has a bug discovered on
day 12, the raw .pb.gz lets us reprocess instead of losing the window. A cycle is
~19 separate protobuf messages, so they are stored with length-prefixed framing
(4-byte big-endian length + message, repeated) — you cannot concatenate protobuf
messages and re-parse them as one, so the frame length is what makes the file
losslessly reprocessable.
"""

from __future__ import annotations

import gzip
import os
import struct
from datetime import datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .service_time import service_date

# Explicit schema so every partition file has identical column types. Schema
# drift across files (e.g. an all-null column inferred as null-type in one file
# and int in another) is what breaks a DuckDB scan over the whole dataset.
VEHICLE_SCHEMA = pa.schema(
    [
        ("entity_id", pa.string()),
        ("vehicle_id", pa.string()),
        ("vehicle_label", pa.string()),
        ("trip_id", pa.string()),
        ("route_id", pa.string()),
        ("direction_id", pa.int32()),
        ("trip_start_date", pa.string()),
        ("trip_start_time", pa.string()),
        ("schedule_relationship", pa.int32()),
        ("latitude", pa.float64()),
        ("longitude", pa.float64()),
        ("bearing", pa.float64()),
        ("speed", pa.float64()),
        ("current_stop_sequence", pa.int64()),
        ("stop_id", pa.string()),
        ("current_status", pa.int32()),
        ("occupancy_status", pa.int32()),
        ("vehicle_ts", pa.int64()),
        ("header_ts", pa.int64()),
        ("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)

_SLOT_MINUTES = 10


def frame_messages(messages: list[bytes]) -> bytes:
    """Concatenate raw protobuf messages with a 4-byte big-endian length prefix each."""
    out = bytearray()
    for msg in messages:
        out.extend(struct.pack(">I", len(msg)))
        out.extend(msg)
    return bytes(out)


def unframe_messages(data: bytes) -> list[bytes]:
    """Inverse of frame_messages — used for reprocessing and in tests."""
    messages: list[bytes] = []
    offset = 0
    while offset < len(data):
        (length,) = struct.unpack_from(">I", data, offset)
        offset += 4
        messages.append(data[offset : offset + length])
        offset += length
    return messages


def slot_bounds(started_at: datetime) -> tuple[datetime, datetime]:
    """Floor the start time to the 10-minute cron slot it belongs to.

    Naming the file by the scheduled slot (not the exact start) is what makes a
    re-run idempotent: a run that fires late at 17:16 still writes the 1710_1720
    slot and overwrites it, rather than creating a duplicate off-by-a-minute file.
    """
    floored = started_at.replace(
        minute=(started_at.minute // _SLOT_MINUTES) * _SLOT_MINUTES,
        second=0,
        microsecond=0,
    )
    return floored, floored + timedelta(minutes=_SLOT_MINUTES)


def _cycle_paths(root: str, slot_start: datetime, slot_end: datetime) -> tuple[Path, Path]:
    dt = service_date(slot_start).isoformat()
    hour = f"{slot_start.hour:02d}"
    name = f"vehicles_{slot_start:%H%M}_{slot_end:%H%M}"
    base = Path(root)
    parquet_path = base / "vehicles" / f"dt={dt}" / f"hour={hour}" / f"{name}.parquet"
    pb_path = base / "pb" / f"dt={dt}" / f"hour={hour}" / f"{name}.pb.gz"
    return parquet_path, pb_path


def _atomic_replace(final: Path, write_tmp) -> None:
    """Write via a .tmp sibling then atomically rename into place."""
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_suffix(final.suffix + ".tmp")
    write_tmp(tmp)
    os.replace(tmp, final)


def write_cycle(
    root: str,
    started_at: datetime,
    rows: list[dict],
    raw_messages: list[bytes],
) -> tuple[Path, Path]:
    """Write the decoded Parquet and the framed raw .pb.gz for one cycle.

    Returns the two paths written. Both are keyed on the 10-minute slot so a
    re-run of the same window overwrites rather than duplicates.
    """
    slot_start, slot_end = slot_bounds(started_at)
    parquet_path, pb_path = _cycle_paths(root, slot_start, slot_end)

    table = pa.Table.from_pylist(rows, schema=VEHICLE_SCHEMA)
    _atomic_replace(
        parquet_path,
        lambda tmp: pq.write_table(table, tmp, compression="zstd"),
    )

    framed = gzip.compress(frame_messages(raw_messages))
    _atomic_replace(pb_path, lambda tmp: tmp.write_bytes(framed))

    return parquet_path, pb_path
