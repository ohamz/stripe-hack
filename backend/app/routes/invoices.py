from __future__ import annotations

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request as HTTPRequest
from sqlmodel import Session, select

from app.billing.webhooks import handle_event, verify_webhook
from app.config import get_settings
from app.db import get_session
from app.models import Client, Decision, Dispute, Invoice, InvoiceLine, Request
from app.schemas import decision_out, dispute_out, invoice_out, line_out

router = APIRouter(prefix="/api")


@router.get("/invoices")
def list_invoices(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(select(Invoice).order_by(Invoice.created_at.desc())).all()
    return [invoice_out(i, session.get(Client, i.client_id)) for i in rows]


@router.get("/invoices/{invoice_id}")
def invoice_detail(invoice_id: int, session: Session = Depends(get_session)) -> dict:
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(404, "No such invoice")
    lines = session.exec(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id).order_by(InvoiceLine.id)).all()
    out_lines = []
    for line in lines:
        d = session.get(Decision, line.decision_id)
        req = session.get(Request, d.request_id)
        disputes = session.exec(select(Dispute).where(Dispute.invoice_line_id == line.id).order_by(Dispute.id)).all()
        out_lines.append({**line_out(line), "decision": decision_out(d), "request_summary": req.summary,
                          "disputes": [dispute_out(x, internal=True) for x in disputes]})
    return {**invoice_out(inv, session.get(Client, inv.client_id)), "lines": out_lines}


@router.post("/stripe/webhook")
async def stripe_webhook(request: HTTPRequest, session: Session = Depends(get_session)) -> dict:
    secret = get_settings().stripe_webhook_secret
    if not secret:
        raise HTTPException(400, "Webhooks are disabled (no STRIPE_WEBHOOK_SECRET); Tab polls Stripe instead.")
    payload = await request.body()
    try:
        event = verify_webhook(payload, request.headers.get("stripe-signature", ""), secret)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(400, f"Invalid webhook: {exc}") from exc
    return {"result": handle_event(session, event)}
