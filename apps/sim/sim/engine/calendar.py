"""Map the simulation's abstract week onto real calendar dates.

The engine runs a seven-day cycle addressed by minute-of-week, which is the
right internal representation: it keeps the tick loop cheap and lets a weekday
be replayed without carrying a date around. But "Tuesday 08:15" with no year is
not something a planner can act on, and it cannot express "last Thursday" or
"the Friday of the Giants game".

So the calendar sits on top. A real instant maps onto a minute-of-week by its
weekday and time, and a minute-of-week maps back onto whichever real date the
caller is asking about. The simulation is unchanged; only the labelling and the
addressing move.

Three things this makes honest rather than implied:

- **Now** is the actual current time in San Francisco, not a session-relative
  offset. Opening the app on a Saturday evening shows a Saturday evening.
- **Looking back** is replay of the modelled week against a past date, and is
  labelled as such. The model has no record of what genuinely happened that
  day; recorded data layers do, and they carry their own dates.
- **Looking forward** is the same weekly pattern projected onto a future date.
  It is a projection from a typical week, not a forecast that knows about
  anything specific to that day unless an event has been added.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

MINUTES_PER_DAY = 1440
DAYS_PER_WEEK = 7
MINUTES_PER_WEEK = MINUTES_PER_DAY * DAYS_PER_WEEK

CITY_TZ = ZoneInfo("America/Los_Angeles")

Horizon = Literal["past", "live", "future"]

DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


def now_local() -> datetime:
    """The current time in San Francisco, which is the city being modelled."""
    return datetime.now(CITY_TZ)


def minute_of_week(moment: datetime) -> int:
    """Where a real instant falls in the simulation's week."""
    return moment.weekday() * MINUTES_PER_DAY + moment.hour * 60 + moment.minute


@dataclass(frozen=True)
class Instant:
    """One point in time, addressed both ways."""

    #: the real date and time this represents
    moment: datetime
    #: the simulation minute that models it
    minute: int
    horizon: Horizon

    @property
    def iso(self) -> str:
        return self.moment.isoformat(timespec="minutes")

    @property
    def day_name(self) -> str:
        return DAY_NAMES[self.moment.weekday()]

    @property
    def label(self) -> str:
        return self.moment.strftime("%a %-d %b %Y, %H:%M") if _supports_dash() else (
            self.moment.strftime("%a %d %b %Y, %H:%M")
        )

    def to_dict(self) -> dict:
        return {
            "iso": self.iso,
            "minute": self.minute,
            "horizon": self.horizon,
            "dayName": self.day_name,
            "label": self.label,
            "daysFromNow": (self.moment.date() - now_local().date()).days,
        }


def _supports_dash() -> bool:
    """Windows strftime rejects %-d, so the label falls back to a padded day."""
    try:
        datetime(2026, 1, 5).strftime("%-d")
        return True
    except ValueError:
        return False


def classify(moment: datetime, tolerance_minutes: int = 45) -> Horizon:
    """Is this moment in the past, close enough to now, or ahead of us?"""
    delta = (moment - now_local()).total_seconds() / 60.0
    if abs(delta) <= tolerance_minutes:
        return "live"
    return "future" if delta > 0 else "past"


def at(moment: datetime) -> Instant:
    """Address a real moment."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=CITY_TZ)
    else:
        moment = moment.astimezone(CITY_TZ)
    return Instant(moment=moment, minute=minute_of_week(moment), horizon=classify(moment))


def live() -> Instant:
    """Right now, in the city."""
    moment = now_local().replace(second=0, microsecond=0)
    return Instant(moment=moment, minute=minute_of_week(moment), horizon="live")


def resolve(
    *,
    iso: str | None = None,
    day_offset: int | None = None,
    weekday: str | None = None,
    hour: int | None = None,
    minute: int = 0,
) -> Instant:
    """Turn whatever a caller said into a real moment.

    Accepts an explicit date, an offset in days, or a named weekday, each
    optionally with a time. Anything omitted is taken from now, so "6pm" means
    six this evening and "Friday" means the coming Friday.
    """
    base = now_local().replace(second=0, microsecond=0)

    if iso:
        try:
            parsed = datetime.fromisoformat(iso)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=CITY_TZ)
            base = parsed.astimezone(CITY_TZ)
        except ValueError:
            pass

    if day_offset is not None:
        base = base + timedelta(days=int(day_offset))

    if weekday:
        wanted = _weekday_index(weekday)
        if wanted is not None:
            ahead = (wanted - base.weekday()) % 7
            # a bare weekday name means the next one, not today, unless it is
            # today and the time asked for has not passed yet
            if ahead == 0 and hour is not None and hour * 60 + minute < base.hour * 60 + base.minute:
                ahead = 7
            base = base + timedelta(days=ahead)

    if hour is not None:
        base = base.replace(hour=int(hour) % 24, minute=int(minute) % 60)

    return at(base)


def _weekday_index(name: str) -> int | None:
    lowered = name.strip().lower()
    for index, day in enumerate(DAY_NAMES):
        if lowered.startswith(day[:3].lower()):
            return index
    if lowered in ("today", "tonight"):
        return now_local().weekday()
    if lowered == "tomorrow":
        return (now_local().weekday() + 1) % 7
    if lowered == "yesterday":
        return (now_local().weekday() - 1) % 7
    return None


def _when(days: int) -> str:
    """Plain words for a day offset, so a same-day jump does not read as zero."""
    if days == 0:
        return "later today"
    if days == 1:
        return "tomorrow"
    if days == -1:
        return "yesterday"
    return f"{abs(days)} days {'ahead' if days > 0 else 'ago'}"


def describe(instant: Instant) -> str:
    """A sentence saying what the viewer is actually looking at."""
    days = instant.to_dict()["daysFromNow"]
    if instant.horizon == "live":
        return (
            f"Showing {instant.label} San Francisco time, which is now. "
            "Agent positions are modelled; the data layers carry their own dates."
        )
    if instant.horizon == "past":
        return (
            f"Looking back at {instant.label}, {_when(days)}. "
            "This replays the modelled typical week against that date. The "
            "simulation has no record of what actually happened that day; the "
            "complaint, incident and permit layers do, and are dated."
        )
    return (
        f"Projecting {instant.label}, {_when(days)}. "
        "This is the modelled typical week applied to that date, not a forecast "
        "of that specific day. Adding a known event changes the projection; "
        "weather, closures and anything else unusual are not in it."
    )
