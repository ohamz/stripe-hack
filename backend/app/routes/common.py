from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session, select

from app.agent.terms import rules_for_client
from app.clock import get_now, period_of
from app.health import compute_health
from app.models import Client, Decision, Request, SourceItem


def client_or_404(session: Session, slug: str) -> Client:
    client = session.exec(select(Client).where(Client.slug == slug)).first()
    if client is None:
        raise HTTPException(404, f"No client '{slug}'")
    return client


def display_period(session: Session) -> str:
    """The latest period up to 'now' that has client requests; else the current period."""
    now_period = period_of(get_now(session))
    periods = sorted({p for p in session.exec(select(Request.period)).all() if p <= now_period})
    return periods[-1] if periods else now_period


def client_decisions(session: Session, client: Client, period: str) -> list[tuple[Request, Decision]]:
    rows = session.exec(
        select(Request, Decision).where(Decision.request_id == Request.id, Request.client_id == client.id,
                                        Request.period == period)
    ).all()
    return sorted(rows, key=lambda r: (r[0].requested_at, r[0].id))


def client_periods(session: Session, client: Client) -> list[str]:
    rows = session.exec(
        select(SourceItem.period).where(SourceItem.client_id == client.id, SourceItem.source.not_in(["contract", "rules"]))
    ).all()
    return sorted(set(rows))


def favour_allowance(session: Session, client: Client) -> int | None:
    for rule in rules_for_client(session, client):
        if rule.params_json and rule.params_json.get("type") == "small_favour":
            return int(rule.params_json["max_per_month"])
    return None


def client_card(session: Session, client: Client, period: str) -> dict:
    decisions = [d for _, d in client_decisions(session, client, period)]
    health = compute_health(decisions)
    return {
        "slug": client.slug,
        "name": client.name,
        "contact_name": client.contact_name,
        "period": period,
        "tab_total_pence": health.amount_billed_pence,
        "favours_used": health.favours_used,
        "favours_free_kind": health.favours_free_kind,
        "favour_allowance": favour_allowance(session, client),
        "needs_review": health.needs_review,
        "health_badge": health.badge if decisions else None,
        "beyond_scope_share_pct": health.beyond_scope_share_pct,
        "decisions": len(decisions),
    }
