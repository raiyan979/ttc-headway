"""One collection cycle: poll the feed every `poll_interval_s` for
`cycle_duration_s`, then write one Parquet + one raw .pb.gz for the window.

Run: `python -m ttc_headway.poll`. Designed to be invoked once per 10-minute
GitHub Actions cron slot; the internal loop is what gets 30-second resolution
out of a scheduler whose finest granularity is 5 minutes.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from .config import Settings
from .feed import build_session, fetch_feed, parse_vehicles
from .r2 import upload_paths
from .service_time import assert_timezone, now_toronto
from .storage import slot_bounds, write_cycle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("ttc_headway.poll")


def run_cycle(settings: Settings) -> int:
    """Run one collection cycle. Returns a process exit code."""
    assert_timezone()
    started_at = now_toronto()
    slot_start, slot_end = slot_bounds(started_at)
    log.info(
        "cycle start: slot %s-%s, interval %ss, duration %ss",
        f"{slot_start:%H:%M}",
        f"{slot_end:%H:%M}",
        settings.poll_interval_s,
        settings.cycle_duration_s,
    )

    session = build_session(settings)
    rows: list[dict] = []
    raw_messages: list[bytes] = []
    attempted = succeeded = 0

    monotonic_start = time.monotonic()
    for offset in range(0, settings.cycle_duration_s + 1, settings.poll_interval_s):
        delay = monotonic_start + offset - time.monotonic()
        if delay > 0:
            time.sleep(delay)

        attempted += 1
        ingested_at = datetime.now(UTC)
        try:
            status, body = fetch_feed(session, settings)
            _, poll_rows = parse_vehicles(body, ingested_at)
            rows.extend(poll_rows)
            raw_messages.append(body)
            succeeded += 1
            log.info("poll %2d: HTTP %s, %d vehicles", attempted, status, len(poll_rows))
        except Exception as e:  # noqa: BLE001 - one bad poll must not abort the cycle
            log.warning("poll %2d failed: %s: %s", attempted, type(e).__name__, e)

    if not rows:
        log.error("no successful polls this cycle; writing nothing (window is a gap)")
        return 1

    parquet_path, pb_path = write_cycle(settings.storage_root, started_at, rows, raw_messages)
    log.info(
        "cycle done: %d/%d polls ok, %d rows -> %s (+ %s)",
        succeeded,
        attempted,
        len(rows),
        parquet_path,
        pb_path.name,
    )

    if settings.r2_configured:
        upload_paths(settings, [parquet_path, pb_path])
    else:
        log.info("R2 not configured; kept local only")
    return 0


def main() -> int:
    return run_cycle(Settings())


if __name__ == "__main__":
    raise SystemExit(main())
