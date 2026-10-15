from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.clock import DEMO_NOW_KEY, get_now, get_setting, period_label, period_of
from app.config import get_settings, llm_key_status, stripe_key_status
from app.db import get_session
from app.models import AgentEvent, Client, Decision, Dispute, Invoice, SourceItem
from app.routes.common import client_card, display_period
from app.schemas import iso

router = APIRouter(prefix="/api")


@router.get("/status")
def status(session: Session = Depends(get_session)) -> dict:
    from app.main import state

    now = get_now(session)
    llm, stripe_status = llm_key_status(), stripe_key_status()
    unprocessed = session.exec(
        select(SourceItem).where(SourceItem.processed_at == None, SourceItem.client_id != None)  # noqa: E711
    ).all()
    return {
        "llm": {"ok": llm.ok, "state": llm.state, "message": llm.message},
        "stripe": {"ok": stripe_status.ok, "state": stripe_status.state, "message": stripe_status.message,
                   "account": state.get("stripe_account"), "webhooks": bool(get_settings().stripe_webhook_secret)},
        "clock": {"now": iso(now), "demo_now": get_setting(session, DEMO_NOW_KEY), "period": period_of(now),
                  "display_period": display_period(session), "display_period_label": period_label(display_period(session))},
        "busy": state.get("busy"),
        "seeded": session.exec(select(Client)).first() is not None,
        "unprocessed_items": len(unprocessed),
        "escalated_disputes": len(session.exec(select(Dispute).where(Dispute.outcome == "escalated")).all()),
    }


@router.get("/overview")
def overview(period: str | None = None, session: Session = Depends(get_session)) -> dict:
    period = period or display_period(session)
    decisions = session.exec(select(Decision).where(Decision.period == period)).all()
    invoices = session.exec(select(Invoice).where(Invoice.period == period)).all()
    clients = session.exec(select(Client).order_by(Client.id)).all()
    return {
        "period": period,
        "period_label": period_label(period),
        "stats": {
            "recovered_pence": sum(d.amount_pence for d in decisions if d.category == "billable"),
            "goodwill_count": sum(1 for d in decisions if d.category == "goodwill"),
            "goodwill_value_pence": sum(d.value_pence for d in decisions if d.category == "goodwill"),
            "needs_review": sum(1 for d in decisions if d.category == "needs_review"),
            "invoices_raised": sum(1 for i in invoices if i.status != "failed"),
            "invoices_paid": sum(1 for i in invoices if i.status == "paid"),
            "invoices_failed": sum(1 for i in invoices if i.status == "failed"),
        },
        "clients": [client_card(session, c, period) for c in clients],
        "unassigned_items": len(session.exec(select(SourceItem).where(SourceItem.client_id == None)).all()),  # noqa: E711
    }


@router.get("/events")
def events(after_id: int = 0, limit: int = 100, session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(
        select(AgentEvent).where(AgentEvent.id > after_id).order_by(AgentEvent.id.desc()).limit(min(limit, 500))
    ).all()
    return [{"id": e.id, "ts": iso(e.ts), "level": e.level, "type": e.type, "message": e.message,
             "payload": e.payload_json} for e in rows]
