"""RIA P1.10.7.2: deterministic validation of structured calendar times."""

import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_AHEAD = timedelta(days=365)


def validate_scheduled_time(scheduled_at, timezone_name, now=None):
    """
    Convert a model-supplied, timezone-aware ISO datetime to Unix seconds.

    No natural-language parsing occurs here.
    """
    if not isinstance(scheduled_at, str) or not scheduled_at.strip():
        raise ValueError("scheduled_at must be a datetime string")

    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError("An IANA timezone is required")

    if len(scheduled_at) > 64 or len(timezone_name) > 100:
        raise ValueError("Datetime or timezone is too long")

    try:
        local_zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise ValueError("Unknown timezone") from exc

    try:
        requested = datetime.fromisoformat(scheduled_at)
    except ValueError as exc:
        raise ValueError("Invalid ISO datetime") from exc

    if requested.tzinfo is None or requested.utcoffset() is None:
        raise ValueError("Datetime must include an explicit UTC offset")

    utc_time = requested.astimezone(timezone.utc)
    localized = utc_time.astimezone(local_zone)

    # The supplied offset and calendar time must match the named zone.
    if (
        localized.replace(tzinfo=None)
        != requested.replace(tzinfo=None)
        or localized.utcoffset() != requested.utcoffset()
    ):
        raise ValueError(
            "Datetime offset does not match the named timezone"
        )

    # Reject times with two possible UTC instants, e.g. DST fallback.
    naive = requested.replace(tzinfo=None)
    possible_offsets = {
        naive.replace(tzinfo=local_zone, fold=fold).utcoffset()
        for fold in (0, 1)
    }
    if len(possible_offsets) != 1:
        raise ValueError("Ambiguous local time requires clarification")

    current = (
        datetime.now(timezone.utc)
        if now is None
        else datetime.fromtimestamp(now, timezone.utc)
    )

    if utc_time <= current:
        raise ValueError("Reminder time is not in the future")

    if utc_time - current > MAX_AHEAD:
        raise ValueError("Reminder exceeds the scheduling window")

    due_at = int(utc_time.timestamp())

    if due_at <= int(current.timestamp()):
        raise ValueError("Reminder must be at least one second ahead")

    return due_at
