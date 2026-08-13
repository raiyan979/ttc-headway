"""One collection cycle: poll the feed every `poll_interval_s` for
`cycle_duration_s`, then write one Parquet + one raw .pb.gz for the window.

Run: `python -m ttc_headway.poll`. Designed to be invoked once per 10-minute
GitHub Actions cron slot; the internal loop is what gets 30-second resolution
out of a scheduler whose finest granularity is 5 minutes.
"""

from __future__ import annotations

import logging
import os
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

    # Fail closed on Actions: a scheduled run that cannot reach R2 would write to
    # the runner's ephemeral disk and silently lose irreplaceable realtime data.
    # Locally (not on Actions), local-only is the intended dev mode.
    if os.getenv("GITHUB_ACTIONS") == "true" and not settings.r2_configured:
        log.error(
            "on GitHub Actions without R2 configured: refusing to collect to "
            "ephemeral storage. Set the TTC_R2_* secrets before enabling the schedule."
        )
        return 2

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
    fetched = parsed = 0

    monotonic_start = time.monotonic()
    for offset in range(0, settings.cycle_duration_s + 1, settings.poll_interval_s):
        delay = monotonic_start + offset - time.monotonic()
        if delay > 0:
            time.sleep(delay)

        ingested_at = datetime.now(UTC)
        try:
            status, body = fetch_feed(session, settings)
        except Exception as e:  # noqa: BLE001 - a bad fetch is just a skipped poll
            log.warning("fetch failed: %s: %s", type(e).__name__, e)
            continue

        # Capture raw bytes BEFORE decoding: the .pb.gz is insurance against a
        # decoder bug, so it must survive even when this decode itself fails.
        raw_messages.append(body)
        fetched += 1
        try:
            _, poll_rows = parse_vehicles(body, ingested_at)
        except Exception as e:  # noqa: BLE001 - keep the raw bytes, drop this poll's rows
            log.warning("parse failed (raw retained): %s: %s", type(e).__name__, e)
            continue
        rows.extend(poll_rows)
        parsed += 1
        log.info("poll: HTTP %s, %d vehicles", status, len(poll_rows))

    if not raw_messages:
        log.error("no successful fetches this cycle; nothing to write (window is a gap)")
        return 1

    parquet_path, pb_path = write_cycle(settings.storage_root, started_at, rows, raw_messages)
    log.info(
        "cycle done: %d fetched, %d parsed, %d rows -> %s (+ %s)",
        fetched,
        parsed,
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
