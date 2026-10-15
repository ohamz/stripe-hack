from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.agent.pipeline import active_periods
from app.clock import get_setting, period_label, set_setting
from app.config import llm_key_status
from app.db import get_session
from app.health import compute_health
from app.memory.cognee_client import LLMKeyMissing, MemoryEmpty
from app.models import Client, ContractTerm, Decision, Invoice, Request, SourceItem, TimeEntry, utcnow
from app.routes.common import client_card, client_decisions, client_or_404, client_periods, display_period
from app.schemas import client_out, decision_out, invoice_out, request_out, source_item_out, term_out, time_entry_out

router = APIRouter(prefix="/api")


@router.get("/clients")
def list_clients(period: str | None = None, session: Session = Depends(get_session)) -> list[dict]:
    period = period or display_period(session)
    return [client_card(session, c, period) for c in session.exec(select(Client).order_by(Client.id)).all()]


@router.get("/clients/{slug}")
def client_detail(slug: str, period: str | None = None, session: Session = Depends(get_session)) -> dict:
    client = client_or_404(session, slug)
    periods = client_periods(session, client)
    period = period or display_period(session)
    active = set(active_periods(session))
    requests = session.exec(select(Request).where(Request.client_id == client.id, Request.period == period)).all()
    decisions = {d.request_id: d for d in session.exec(select(Decision).where(Decision.period == period)).all()}
    items = session.exec(
        select(SourceItem).where(SourceItem.client_id == client.id, SourceItem.period == period,
                                 SourceItem.source.not_in(["contract", "rules"]))
    ).all()
    request_item_ids = {r.source_item_id for r in requests}
    pending = [i for i in items if i.processed_at is None and i.source in ("slack", "email", "simulated")]
    not_requests = [i for i in items if i.processed_at is not None and i.source in ("slack", "email", "simulated")
                    and i.id not in request_item_ids]
    entries = session.exec(select(TimeEntry).where(TimeEntry.client_id == client.id)).all()
    entry_items = {e.source_item_id: e for e in entries}
    unmatched = [time_entry_out(entry_items[i.id]) for i in items if i.source == "timelog" and i.id in entry_items
                 and entry_items[i.id].request_id is None]
    invoices = session.exec(select(Invoice).where(Invoice.client_id == client.id).order_by(Invoice.period.desc())).all()
    terms = session.exec(select(ContractTerm).where(ContractTerm.client_id == client.id)).all()
    return {
        "client": client_out(client),
        "card": client_card(session, client, period),
        "terms": [term_out(t) for t in terms],
        "periods": [{"period": p, "label": period_label(p), "history": p not in active} for p in periods],
        "period": period,
        "period_label": period_label(period),
        "is_history": period not in active,
        "requests": [request_out(session, r, decisions) for r in sorted(requests, key=lambda r: (r.requested_at, r.id), reverse=True)],
        "pending_items": [source_item_out(i) for i in sorted(pending, key=lambda i: i.occurred_at, reverse=True)],
        "not_requests": [source_item_out(i) for i in sorted(not_requests, key=lambda i: i.occurred_at, reverse=True)],
        "history_items": [source_item_out(i) for i in sorted(items, key=lambda i: i.occurred_at, reverse=True)]
        if period not in active else [],
        "unmatched_time": unmatched,
        "invoices": [invoice_out(i) for i in invoices],
        "llm_ok": llm_key_status().ok,
    }


def _narrative_key(client: Client, period: str) -> str:
    return f"health_narrative:{client.id}:{period}"


@router.get("/clients/{slug}/health")
def client_health(slug: str, period: str | None = None, session: Session = Depends(get_session)) -> dict:
    client = client_or_404(session, slug)
    period = period or display_period(session)
    numbers = compute_health([d for _, d in client_decisions(session, client, period)])
    cached = json.loads(get_setting(session, _narrative_key(client, period), "null") or "null")
    narrative = cached if cached and cached.get("numbers") == numbers.to_dict() else None
    return {"period": period, "period_label": period_label(period), "numbers": numbers.to_dict(),
            "has_decisions": numbers.minutes_total > 0 or bool(client_decisions(session, client, period)),
            "narrative": narrative, "llm_ok": llm_key_status().ok}


@router.post("/clients/{slug}/health/narrative")
async def client_health_narrative(slug: str, period: str | None = None, session: Session = Depends(get_session)) -> dict:
    from app.agent.explain import health_narrative

    client = client_or_404(session, slug)
    period = period or display_period(session)
    numbers = compute_health([d for _, d in client_decisions(session, client, period)])
    try:
        result = await health_narrative(session, client, period, numbers)
    except LLMKeyMissing as exc:
        raise HTTPException(503, str(exc)) from exc
    except MemoryEmpty as exc:
        raise HTTPException(409, f"Memory is empty: {exc}") from exc
    payload = {"numbers": numbers.to_dict(), **result, "generated_at": utcnow().isoformat()}
    set_setting(session, _narrative_key(client, period), json.dumps(payload))
    return payload


@router.get("/source-items/{item_id}")
def source_item(item_id: int, session: Session = Depends(get_session)) -> dict:
    item = session.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(404, "No such source item")
    out = source_item_out(item)
    entry = session.exec(select(TimeEntry).where(TimeEntry.source_item_id == item.id)).first()
    out["time_entry"] = time_entry_out(entry) if entry else None
    out["client"] = client_out(session.get(Client, item.client_id)) if item.client_id else None
    return out


@router.get("/time-entries/{entry_id}")
def time_entry(entry_id: int, session: Session = Depends(get_session)) -> dict:
    entry = session.get(TimeEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "No such time entry")
    return {**time_entry_out(entry), "source_item": source_item_out(session.get(SourceItem, entry.source_item_id))}


@router.get("/unassigned")
def unassigned(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(select(SourceItem).where(SourceItem.client_id == None).order_by(SourceItem.occurred_at)).all()  # noqa: E711
    return [source_item_out(i) for i in rows]


@router.get("/decisions/{decision_id}")
def decision(decision_id: int, session: Session = Depends(get_session)) -> dict:
    d = session.get(Decision, decision_id)
    if d is None:
        raise HTTPException(404, "No such decision")
    return {**decision_out(d), "request": request_out(session, session.get(Request, d.request_id), {d.request_id: d})}
