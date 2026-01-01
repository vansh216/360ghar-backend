"""
Core utility functions.

Shared helper functions used across the application.
"""

from datetime import datetime, timezone


def make_tz_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC).

    Handles both naive and aware datetimes. If the datetime is naive
    (has no timezone info), it is assumed to be UTC and marked as such.

    Args:
        dt: A datetime object, which may be timezone-naive or aware.

    Returns:
        A timezone-aware datetime in UTC, or None if input is None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
