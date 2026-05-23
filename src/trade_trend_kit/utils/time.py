"""Time and timezone helpers.

Centralized time helpers keep scheduled jobs, file paths, and reports on the
same configured timezone.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Shanghai"


def get_timezone(timezone_name: str | ZoneInfo = DEFAULT_TIMEZONE) -> ZoneInfo:
    """Return a ZoneInfo instance from a configured timezone name."""

    if isinstance(timezone_name, ZoneInfo):
        return timezone_name
    return ZoneInfo(timezone_name)


def to_timezone(
    value: datetime,
    timezone_name: str | ZoneInfo = DEFAULT_TIMEZONE,
) -> datetime:
    """Convert a datetime into the project timezone, assuming naive values are local."""

    timezone = get_timezone(timezone_name)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def date_key(
    value: datetime,
    timezone_name: str | ZoneInfo = DEFAULT_TIMEZONE,
) -> str:
    """Return the YYYY-MM-DD storage partition for a datetime."""

    return to_timezone(value, timezone_name).date().isoformat()


def now_in_timezone(timezone_name: str | ZoneInfo = DEFAULT_TIMEZONE) -> datetime:
    """Return the current timezone-aware datetime."""

    return datetime.now(get_timezone(timezone_name))
