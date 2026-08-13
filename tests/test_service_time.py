"""Service-day logic, including the DST boundary.

The DST test is not optional (plan §14): the service day runs 04:00-03:59 and so
spans 02:00, where Canada shifts the clock twice a year. Getting the conversion
wrong silently mislabels an hour of overnight data.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from ttc_headway.service_time import service_date

TORONTO = ZoneInfo("America/Toronto")


def test_after_cutoff_is_same_calendar_date():
    dt = datetime(2026, 8, 14, 10, 0, tzinfo=TORONTO)
    assert service_date(dt).isoformat() == "2026-08-14"


def test_before_cutoff_rolls_back():
    dt = datetime(2026, 8, 14, 1, 30, tzinfo=TORONTO)
    assert service_date(dt).isoformat() == "2026-08-13"


def test_boundary_exactly_at_cutoff_is_same_day():
    assert service_date(datetime(2026, 8, 14, 4, 0, tzinfo=TORONTO)).isoformat() == "2026-08-14"
    assert service_date(datetime(2026, 8, 14, 3, 59, tzinfo=TORONTO)).isoformat() == "2026-08-13"


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        service_date(datetime(2026, 8, 14, 10, 0))


def test_input_in_utc_is_converted_to_toronto():
    # 2026-08-14 06:30 UTC is 02:30 Toronto (EDT) -> before cutoff -> prior day.
    dt = datetime(2026, 8, 14, 6, 30, tzinfo=UTC)
    assert service_date(dt).isoformat() == "2026-08-13"


def test_dst_spring_forward():
    # 2026-03-08 the clock jumps 02:00 EST -> 03:00 EDT at 07:00 UTC.
    # 07:00 UTC is 03:00 local (EDT), hour < 4 -> previous service day.
    assert service_date(datetime(2026, 3, 8, 7, 0, tzinfo=UTC)).isoformat() == "2026-03-07"
    # 09:00 UTC is 05:00 local, hour >= 4 -> same day.
    assert service_date(datetime(2026, 3, 8, 9, 0, tzinfo=UTC)).isoformat() == "2026-03-08"


def test_dst_fall_back_repeated_hour_belongs_to_prior_service_day():
    # 2026-11-01 the clock falls 02:00 EDT -> 01:00 EST at 06:00 UTC, so 01:30
    # local happens twice. Both instants are before the 04:00 cutoff and must
    # map to the Oct 31 service day, never the calendar date Nov 1.
    before = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)  # 01:30 EDT
    after = datetime(2026, 11, 1, 6, 30, tzinfo=UTC)  # 01:30 EST (repeat)
    assert service_date(before).isoformat() == "2026-10-31"
    assert service_date(after).isoformat() == "2026-10-31"
