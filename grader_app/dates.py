"""Dates in English whatever the computer's language. Python's %b and %a follow the system language once the
app starts (on a Turkish Mac "Oct" becomes "Eki"), so month names are written out here instead."""
from __future__ import annotations

import datetime as _dt

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def day_month(d: _dt.date | _dt.datetime, year: bool = True) -> str:
    """'23 Oct 2026', or '23 Oct' without the year."""
    return f"{d.day} {MONTHS[d.month - 1]}" + (f" {d.year}" if year else "")


def stamp(ts: float | _dt.datetime, year: bool = True) -> str:
    """'23 Oct 2026, 08:30' from a timestamp or a datetime."""
    d = ts if isinstance(ts, _dt.datetime) else _dt.datetime.fromtimestamp(float(ts))
    return f"{day_month(d, year)}, {d.hour:02d}:{d.minute:02d}"
