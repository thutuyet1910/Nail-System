
from datetime import date, datetime
from zoneinfo import ZoneInfo

SALON_TZ = ZoneInfo("America/Phoenix")


def now_local() -> datetime:
    return datetime.now(SALON_TZ).replace(tzinfo=None)


def today_local() -> date:
    return datetime.now(SALON_TZ).date()