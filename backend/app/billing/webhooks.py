"""Payment status: Stripe webhooks when STRIPE_WEBHOOK_SECRET is set, otherwise polling every 60 seconds."""

from __future__ import annotations

import asyncio

import stripe
from sqlmodel import Session, select

from app.billing.stripe_client import configure
from app.events import emit
from app.models import Client, Invoice

STATUS_FROM_STRIPE = {"paid": "paid", "void": "void", "open": "open", "draft": "draft"}


def apply_status(session: Session, invoice: Invoice, stripe_status: str, source: str) -> bool:
    new = STATUS_FROM_STRIPE.get(stripe_status)
    if new is None or new == invoice.status:
        return False
    old, invoice.status = invoice.status, new
    session.add(invoice)
    session.commit()
    client = session.get(Client, invoice.client_id)
    emit(session, "invoice_status", f"{client.name} invoice for {invoice.period} is now {new} (was {old}, via {source}).",
         client=client.slug, invoice_id=invoice.id, stripe_invoice_id=invoice.stripe_invoice_id)
    return True


def handle_event(session: Session, event: dict) -> str:
    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    invoice = session.exec(select(Invoice).where(Invoice.stripe_invoice_id == obj.get("id"))).first()
    if invoice is None:
        return "ignored: unknown invoice"
    if etype == "invoice.paid":
        apply_status(session, invoice, "paid", "webhook")
    elif etype == "invoice.voided":
        apply_status(session, invoice, "void", "webhook")
    elif etype == "invoice.payment_failed":
        client = session.get(Client, invoice.client_id)
        emit(session, "invoice_payment_failed", f"A payment attempt on the {client.name} invoice failed.", level="warn",
             client=client.slug, invoice_id=invoice.id)
    else:
        return f"ignored: {etype}"
    return "ok"


def verify_webhook(payload: bytes, signature: str, secret: str) -> dict:
    """Raises stripe.SignatureVerificationError or ValueError on a bad request."""
    event = stripe.Webhook.construct_event(payload, signature, secret)
    return event.to_dict() if hasattr(event, "to_dict") else dict(event)


def _poll_sync(invoice_ids: list[tuple[int, str]]) -> list[tuple[int, str]]:
    configure()
    return [(inv_id, stripe.Invoice.retrieve(stripe_id).status) for inv_id, stripe_id in invoice_ids]


async def poll_open_invoices(session: Session) -> int:
    open_invoices = session.exec(select(Invoice).where(Invoice.status == "open", Invoice.stripe_invoice_id != None)).all()  # noqa: E711
    if not open_invoices:
        return 0
    statuses = await asyncio.to_thread(_poll_sync, [(i.id, i.stripe_invoice_id) for i in open_invoices])
    changed = 0
    for inv_id, status in statuses:
        changed += apply_status(session, session.get(Invoice, inv_id), status, "polling")
    return changed
