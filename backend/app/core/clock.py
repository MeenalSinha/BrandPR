"""Single source of 'now' so date rules are deterministic and testable.

today() honours CLOCK_OFFSET_DAYS (a testing aid, refused in production) so date rules such as fact expiry can be exercised
against a running server. now() is never shifted: stored timestamps always record real time.
"""
from datetime import date, datetime, timedelta, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    from app.core.config import get_settings  # imported lazily: config does not depend on this module

    return (now() + timedelta(days=get_settings().clock_offset_days)).date()
