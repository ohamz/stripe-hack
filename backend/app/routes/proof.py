"""The client's proof page (no internal data: no Cognee context, no outcome reasoning)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.agent.terms import contract_item
from app.clock import fmt_day, fmt_london, period_label
from app.connectors.contract import parse_clauses
from app.db import get_session
from app.ingest import registry
from app.memory.formatting import channel_of
from app.models import Client, Decision, Dispute, Invoice, InvoiceLine, Request, SourceItem, TimeEntry
from app.schemas import DisputeBody, dispute_out

router = APIRouter(prefix="/api")


def _invoice_by_token(session: Session, token: str) -> Invoice:
    inv = session.exec(select(Invoice).where(Invoice.proof_token == token)).first()
    if inv is None or len(token) < 24:
        raise HTTPException(404, "This proof link is not valid.")
    return inv


@router.get("/proof/{token}")
def proof(token: str, session: Session = Depends(get_session)) -> dict:
    inv = _invoice_by_token(session, token)
    client = session.get(Client, inv.client_id)
    contract = contract_item(session, client)
    clauses = parse_clauses(contract.text) if contract else {}
    freelancer = registry().freelancer
    lines = session.exec(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id).order_by(InvoiceLine.id)).all()
    extra, on_house = [], []
    for line in lines:
        d = session.get(Decision, line.decision_id)
        req = session.get(Request, d.request_id)
        item = session.get(SourceItem, req.source_item_id)
        entries = session.exec(select(TimeEntry).where(TimeEntry.request_id == req.id)).all()
        disputes = session.exec(select(Dispute).where(Dispute.invoice_line_id == line.id).order_by(Dispute.id)).all()
        entry = {
            "line_id": line.id,
            "description": line.description,
            "amount_pence": line.amount_pence,
            "value_pence": d.value_pence,
            "summary": req.summary,
            "evidence": {
                "message": {"quote": req.quote, "date": fmt_london(item.occurred_at), "day": fmt_day(item.occurred_at),
                            "source": item.source, "channel": channel_of(item), "author": item.author,
                            "simulated": item.source == "simulated"},
                "time": [{"date": fmt_london(t.started_at), "minutes": t.minutes, "description": t.description} for t in entries]
                or ([{"date": fmt_london(item.occurred_at), "minutes": d.minutes_logged,
                      "description": f"Calendar: {item.title}"}] if req.kind == "meeting" else []),
                "minutes_logged": d.minutes_logged,
                "minutes_billed": d.minutes_billed,
                "clauses": [{"ref": r, "text": clauses.get(r, "")} for r in d.clause_refs],
                "explanation": d.explanation,
            },
            "disputes": [dispute_out(x, internal=False) for x in disputes],
        }
        (on_house if line.is_goodwill else extra).append(entry)
    return {
        "business_name": freelancer.get("business_name", ""),
        "freelancer_name": freelancer.get("name", ""),
        "client_name": client.name,
        "period": inv.period,
        "period_label": period_label(inv.period),
        "total_pence": inv.total_pence,
        "goodwill_value_pence": inv.goodwill_value_pence,
        "status": inv.status,
        "hosted_invoice_url": inv.hosted_invoice_url,
        "extra_work": extra,
        "on_the_house": on_house,
    }


@router.post("/proof/{token}/disputes")
async def dispute(token: str, body: DisputeBody, session: Session = Depends(get_session)) -> dict:
    from app.agent.explain import handle_dispute

    inv = _invoice_by_token(session, token)
    line = session.get(InvoiceLine, body.line_id)
    if line is None or line.invoice_id != inv.id:
        raise HTTPException(404, "No such line on this invoice.")
    if line.is_goodwill:
        raise HTTPException(400, "This line is free of charge.")
    result = await handle_dispute(session, line, body.message.strip(), session.get(Client, inv.client_id))
    return dispute_out(result, internal=False)
