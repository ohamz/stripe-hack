"""Client health numbers (PLAN.md 10.2). Deterministic; the LLM only writes the narrative."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.models import Decision


@dataclass
class HealthNumbers:
    minutes_total: int
    minutes_in_scope: int
    minutes_beyond_scope: int
    hours_total: float
    hours_in_scope: float
    hours_beyond_scope: float
    beyond_scope_share_pct: float  # one decimal place
    favours_used: int  # goodwill decisions that use the allowance
    favours_free_kind: int  # goodwill decisions that don't (e.g. G2 typo fixes)
    favours_value_pence: int
    amount_billed_pence: int
    needs_review: int
    badge: str

    def to_dict(self) -> dict:
        return asdict(self)


def badge_for(share_pct: float) -> str:
    if share_pct < 20:
        return "Healthy"
    if share_pct <= 50:
        return "Watch"
    return "Over scope"


def compute_health(decisions: list[Decision]) -> HealthNumbers:
    total = sum(d.minutes_logged for d in decisions)
    in_scope = sum(d.minutes_logged for d in decisions if d.category == "included")
    beyond = sum(d.minutes_logged for d in decisions if d.category in ("billable", "goodwill"))
    share = round(beyond * 100 / total, 1) if total else 0.0
    goodwill = [d for d in decisions if d.category == "goodwill"]
    return HealthNumbers(
        minutes_total=total,
        minutes_in_scope=in_scope,
        minutes_beyond_scope=beyond,
        hours_total=round(total / 60, 2),
        hours_in_scope=round(in_scope / 60, 2),
        hours_beyond_scope=round(beyond / 60, 2),
        beyond_scope_share_pct=share,
        favours_used=sum(1 for d in goodwill if d.counts_towards_allowance),
        favours_free_kind=sum(1 for d in goodwill if not d.counts_towards_allowance),
        favours_value_pence=sum(d.value_pence for d in goodwill),
        amount_billed_pence=sum(d.amount_pence for d in decisions if d.category == "billable"),
        needs_review=sum(1 for d in decisions if d.category == "needs_review"),
        badge=badge_for(share),
    )


def allowed_numbers(h: HealthNumbers) -> set[str]:
    """Every textual form of a number the narrative may use."""
    out: set[str] = set()

    def add(x: float) -> None:
        for s in {f"{x:g}", f"{x:.1f}", f"{x:.2f}", str(int(round(x)))}:
            out.add(s)
            out.add(s.rstrip("0").rstrip(".") if "." in s else s)

    for v in (h.minutes_total, h.minutes_in_scope, h.minutes_beyond_scope, h.hours_total, h.hours_in_scope,
              h.hours_beyond_scope, h.beyond_scope_share_pct, h.favours_used, h.favours_free_kind, h.needs_review,
              h.favours_used + h.favours_free_kind):
        add(float(v))
    for pence in (h.amount_billed_pence, h.favours_value_pence):
        add(pence / 100)
        out.add(f"{pence / 100:,.2f}")
    return out


_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def unverified_numbers(text: str, h: HealthNumbers) -> list[str]:
    allowed = allowed_numbers(h)
    bad = []
    for m in _NUMBER_RE.findall(text):
        token = m.rstrip(".,")
        if token not in allowed and token.replace(",", "") not in allowed:
            bad.append(token)
    return bad
