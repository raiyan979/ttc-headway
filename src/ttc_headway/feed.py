"""Fetch and parse the GTFS-Realtime vehicle feed.

Two responsibilities, kept separate so tests can parse committed .pb fixtures
without any network: `fetch_feed` does the hardened HTTP GET, `parse_vehicles`
turns raw bytes into row dicts. The raw layer stays faithful to the source —
unset fields stay null, no cleaning or clamping here (that is the staging
layer's job in Phase 3).
"""

from __future__ import annotations

from datetime import datetime

import requests
from google.transit import gtfs_realtime_pb2
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Settings


def build_session(settings: Settings) -> requests.Session:
    """A session with bounded retries, exponential backoff + jitter, and
    Retry-After respected on 429/503."""
    retry = Retry(
        total=settings.max_retries,
        backoff_factor=0.5,
        backoff_jitter=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers["User-Agent"] = settings.user_agent
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class ResponseTooLarge(Exception):
    """The response exceeded the configured byte cap before it finished."""


def fetch_feed(session: requests.Session, settings: Settings) -> tuple[int, bytes]:
    """GET the feed, streaming with a hard size cap. Returns (http_status, body).

    Streaming + a running byte count means a hostile or malfunctioning endpoint
    cannot exhaust memory: we stop reading once the cap is exceeded rather than
    trusting a (spoofable) Content-Length header.
    """
    timeout = (settings.connect_timeout_s, settings.read_timeout_s)
    with session.get(settings.feed_url, timeout=timeout, stream=True) as resp:
        status = resp.status_code
        body = bytearray()
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            body.extend(chunk)
            if len(body) > settings.max_response_bytes:
                raise ResponseTooLarge(f"response exceeded {settings.max_response_bytes} bytes")
    return status, bytes(body)


def _direction_id(trip: gtfs_realtime_pb2.TripDescriptor) -> int | None:
    return trip.direction_id if trip.HasField("direction_id") else None


def parse_vehicles(raw: bytes, ingested_at: datetime) -> tuple[int, list[dict]]:
    """Parse a feed response into (header_timestamp, vehicle rows).

    `ingested_at` is our wall-clock capture time; `header_timestamp` is the
    feed's own generation time. Keeping both is what lets the staging layer
    detect vehicle clock drift later.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw)
    header_ts = feed.header.timestamp

    rows: list[dict] = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        trip = v.trip
        pos = v.position
        rows.append(
            {
                "entity_id": entity.id,
                "vehicle_id": v.vehicle.id or None,
                "vehicle_label": v.vehicle.label or None,
                "trip_id": trip.trip_id or None,
                "route_id": trip.route_id or None,
                "direction_id": _direction_id(trip),
                "trip_start_date": trip.start_date or None,
                "trip_start_time": trip.start_time or None,
                "schedule_relationship": (
                    trip.schedule_relationship if trip.HasField("schedule_relationship") else None
                ),
                "latitude": pos.latitude if v.HasField("position") else None,
                "longitude": pos.longitude if v.HasField("position") else None,
                "bearing": pos.bearing if pos.HasField("bearing") else None,
                "speed": pos.speed if pos.HasField("speed") else None,
                "current_stop_sequence": (
                    v.current_stop_sequence if v.HasField("current_stop_sequence") else None
                ),
                "stop_id": v.stop_id or None,
                "current_status": (v.current_status if v.HasField("current_status") else None),
                "occupancy_status": (
                    v.occupancy_status if v.HasField("occupancy_status") else None
                ),
                "vehicle_ts": v.timestamp if v.HasField("timestamp") else None,
                "header_ts": header_ts,
                "ingested_at": ingested_at,
            }
        )
    return header_ts, rows
