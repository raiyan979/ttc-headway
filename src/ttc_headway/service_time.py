"""Service-day time logic.

The whole pipeline is keyed on *service date*, not calendar date. GTFS models a
service day as running from 04:00 to 03:59 the next morning: a streetcar trip
that departs at 01:30 belongs to the *previous* day's service. Partitioning on
calendar date instead would smear every overnight number across two dates.

Timezone is America/Toronto, hardcoded — never system-local. A pipeline whose
output depends on which machine ran it is broken, and this one spans a DST
boundary during the collection window.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TIMEZONE = "America/Toronto"
# A trip before 04:00 belongs to the previous service day.
SERVICE_DAY_CUTOFF_HOUR = 4


def assert_timezone() -> ZoneInfo:
    """Load the Toronto zone, failing loudly at startup if the tz database is missing.

    On Windows there is no system IANA database; the `tzdata` package supplies it.
    Asserting here means a misconfigured environment fails immediately, not silently
    with wrong partition dates.
    """
    try:
        return ZoneInfo(TIMEZONE)
    except ZoneInfoNotFoundError as e:  # pragma: no cover - environment failure
        raise RuntimeError(
            f"Timezone {TIMEZONE!r} unavailable. Install the 'tzdata' package."
        ) from e


def now_toronto() -> datetime:
    """Current time as a timezone-aware datetime in Toronto local time."""
    return datetime.now(ZoneInfo(TIMEZONE))


def service_date(moment: datetime) -> date:
    """Return the service date for an instant.

    Accepts any timezone-aware datetime, converts to Toronto, and rolls times
    before the 04:00 cutoff back to the previous calendar date.
    """
    if moment.tzinfo is None:
        raise ValueError("service_date requires a timezone-aware datetime")
    local = moment.astimezone(ZoneInfo(TIMEZONE))
    if local.hour < SERVICE_DAY_CUTOFF_HOUR:
        return (local - timedelta(days=1)).date()
    return local.date()
