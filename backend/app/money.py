"""Deterministic money maths (PLAN.md 8.3). Integer pence only; never done by the LLM."""

from __future__ import annotations

import math


def billed_minutes(minutes_logged: int, increment_minutes: int) -> int:
    """Round up to the billing increment, per task (clause 5.3)."""
    if increment_minutes <= 0:
        raise ValueError("billing increment must be positive")
    if minutes_logged < 0:
        raise ValueError("minutes cannot be negative")
    return math.ceil(minutes_logged / increment_minutes) * increment_minutes


def value_pence(minutes_billed: int, hourly_rate_pence: int) -> int:
    """minutes_billed * rate / 60, exact in integer pence.

    Raises if the result isn't a whole number of pence, instead of silently rounding money.
    """
    total = minutes_billed * hourly_rate_pence
    if total % 60:
        raise ValueError(f"{minutes_billed} min at {hourly_rate_pence}p/h is not a whole number of pence")
    return total // 60


def format_gbp(pence: int) -> str:
    sign = "-" if pence < 0 else ""
    pence = abs(pence)
    return f"{sign}£{pence // 100:,}.{pence % 100:02d}"


def format_rate(hourly_rate_pence: int) -> str:
    """'£50/h' for whole pounds, '£52.50/h' otherwise."""
    if hourly_rate_pence % 100 == 0:
        return f"£{hourly_rate_pence // 100}/h"
    return f"{format_gbp(hourly_rate_pence)}/h"
