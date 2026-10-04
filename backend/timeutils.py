from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_SALON_TIMEZONE = "America/Phoenix"


def salon_zone(timezone_name: str = DEFAULT_SALON_TIMEZONE) -> tzinfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        # Some Windows Python installations do not ship the IANA database.
        # Phoenix is fixed at MST (UTC-07:00) and does not observe DST, so this
        # fallback is exact for the application's required salon timezone.
        if timezone_name == DEFAULT_SALON_TIMEZONE:
            return timezone(timedelta(hours=-7), name=DEFAULT_SALON_TIMEZONE)
        raise


def as_salon_datetime(value: datetime, timezone_name: str = DEFAULT_SALON_TIMEZONE) -> datetime:
    zone = salon_zone(timezone_name)
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def local_to_utc_naive(value: datetime, timezone_name: str = DEFAULT_SALON_TIMEZONE) -> datetime:
    return as_salon_datetime(value, timezone_name).astimezone(timezone.utc).replace(tzinfo=None)


def utc_naive_to_local(value: datetime, timezone_name: str = DEFAULT_SALON_TIMEZONE) -> datetime:
    return value.replace(tzinfo=timezone.utc).astimezone(salon_zone(timezone_name))


def local_day_bounds_utc(day: date, timezone_name: str = DEFAULT_SALON_TIMEZONE) -> tuple[datetime, datetime]:
    zone = salon_zone(timezone_name)
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day, time.max, tzinfo=zone)
    return (
        start.astimezone(timezone.utc).replace(tzinfo=None),
        end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---- Salon business clock ------------------------------------------------------------------
# Business-day decisions (today's Turns, fairness, income day, "is this start in the past?")
# must follow the salon's wall clock, never the host's. Persisted *instants* stay UTC (see
# utc_now_naive); the naive "salon local" values below match the legacy Turn/Checkout columns.
def _utc_now_aware() -> datetime:
    """The single clock source for the salon helpers. Tests patch this one function."""
    return datetime.now(timezone.utc)


def salon_now(timezone_name: str = DEFAULT_SALON_TIMEZONE) -> datetime:
    """Current time as an aware datetime in the salon timezone."""
    return _utc_now_aware().astimezone(salon_zone(timezone_name))


def salon_naive_now(timezone_name: str = DEFAULT_SALON_TIMEZONE) -> datetime:
    """Current salon wall-clock time without tzinfo (legacy Turn/Checkout column convention)."""
    return salon_now(timezone_name).replace(tzinfo=None)


def salon_today(timezone_name: str = DEFAULT_SALON_TIMEZONE) -> date:
    return salon_now(timezone_name).date()
