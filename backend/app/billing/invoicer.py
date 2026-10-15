"""Step 7: the billing job (PLAN.md 9.1). No human raises the bill.

Double-billing guard: the Invoice row (unique on client_id + period) is inserted *before* any Stripe call,
so a second run, a crash or a concurrent run can never raise a second invoice for the same client and period.
A failed run leaves a 'failed' row and is never retried automatically.
"""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field

import stripe
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.agent.terms import TermsIncomplete, load_terms
from app.billing.stripe_client import configure
from app.clock import fmt_day, get_now, get_setting, is_period_closed_for_billing, period_label, set_setting
from app.config import get_settings, stripe_key_status
from app.db import session_scope
from app.events import emit
from app.memory import cognee_client
from app.memory.formatting import invoice_record
from app.models import Client, Decision, Invoice, InvoiceLine, Request, utcnow
from app.money import format_gbp, format_rate

CUSTOM_FIELD_NAME = "Proof of work"  # Stripe: name <= 40 chars, value <= 140 chars, up to 4 fields


@dataclass
class PlannedLine:
    decision_id: int
    description: str
    amount_pence: int
    is_goodwill: bool
    value_pence: int


@dataclass
class InvoicePlan:
    billable: list[PlannedLine] = field(default_factory=list)
    goodwill: list[PlannedLine] = field(default_factory=list)
    needs_review: int = 0

    @property
    def total_pence(self) -> int:
        return sum(line.amount_pence for line in self.billable)

    @property
    def goodwill_value_pence(self) -> int:
        return sum(line.value_pence for line in self.goodwill)


def billable_description(summary: str, day: str, minutes_billed: int, rate_pence: int, refs: list[str]) -> str:
    return f"{summary} ({day}, {minutes_billed} min @ {format_rate(rate_pence)}, clause {', '.join(refs)})"


def goodwill_description(summary: str, day: str, value_pence: int) -> str:
    return f"On the house: {summary} ({day}, worth {format_gbp(value_pence)})"


def plan_invoice(session: Session, client: Client, period: str, hourly_rate_pence: int) -> InvoicePlan:
    rows = session.exec(
        select(Decision, Request).where(Decision.request_id == Request.id, Request.client_id == client.id,
                                        Decision.period == period)
    ).all()
    plan = InvoicePlan()
    for decision, req in sorted(rows, key=lambda r: (r[1].requested_at, r[1].id)):
        day = fmt_day(req.requested_at)
        if decision.category == "billable":
            plan.billable.append(PlannedLine(decision.id, billable_description(
                req.summary, day, decision.minutes_billed, hourly_rate_pence, decision.clause_refs),
                decision.amount_pence, False, decision.value_pence))
        elif decision.category == "goodwill":
            plan.goodwill.append(PlannedLine(decision.id, goodwill_description(req.summary, day, decision.value_pence),
                                             0, True, decision.value_pence))
        elif decision.category == "needs_review":
            plan.needs_review += 1
    return plan


def claim_invoice_slot(session: Session, client: Client, period: str) -> Invoice | None:
    """Insert the Invoice row first. Returns None if one already exists for (client, period)."""
    if session.exec(select(Invoice).where(Invoice.client_id == client.id, Invoice.period == period)).first():
        return None
    invoice = Invoice(client_id=client.id, period=period, status="draft", proof_token=secrets.token_urlsafe(24))
    session.add(invoice)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    session.refresh(invoice)
    return invoice


def _ensure_customer(session: Session, client: Client) -> str:
    if client.stripe_customer_id:
        return client.stripe_customer_id
    customer = stripe.Customer.create(
        name=client.name, email=client.contact_email, metadata={"tab_client_id": str(client.id)},
        idempotency_key=f"tab-customer-{client.id}-{client.slug}",
    )
    client.stripe_customer_id = customer.id
    session.add(client)
    session.commit()
    return customer.id


def _create_stripe_invoice(customer_id: str, invoice: Invoice, terms_days: int, proof_url: str, notes: list[str]):
    # Idempotency keys use the random proof token, not the row id: row ids restart after `make reset`,
    # and Stripe rejects a reused key with different parameters for 24 hours.
    base = dict(
        customer=customer_id,
        collection_method="send_invoice",
        days_until_due=terms_days,
        currency="gbp",
        description=f"Extra work for {period_label(invoice.period)}. See the evidence for every line: {proof_url}",
        metadata={"tab_invoice_id": str(invoice.id), "period": invoice.period},
    )
    if len(proof_url) <= 140:
        try:
            return stripe.Invoice.create(**base, custom_fields=[{"name": CUSTOM_FIELD_NAME, "value": proof_url}],
                                         idempotency_key=f"tab-invoice-{invoice.proof_token}-cf")
        except stripe.InvalidRequestError as exc:
            notes.append(f"Stripe rejected the 'Proof of work' custom field, created without it: {exc.user_message or exc}")
    else:
        notes.append(f"Proof URL is {len(proof_url)} chars (custom field limit 140); custom field skipped.")
    return stripe.Invoice.create(**base, idempotency_key=f"tab-invoice-{invoice.proof_token}-nocf")


def raise_invoice_sync(client_id: int, period: str) -> dict:
    """Runs in a worker thread (the Stripe library is synchronous). Returns a summary for logging."""
    settings = get_settings()
    with session_scope() as session:
        client = session.get(Client, client_id)
        terms = load_terms(session, client)
        plan = plan_invoice(session, client, period, terms.hourly_rate_pence)
        label = period_label(period)
        if plan.needs_review:
            key = f"billing_review_warned:{client.id}:{period}"
            if not get_setting(session, key):
                emit(session, "billing_review", f"{plan.needs_review} {client.name} item(s) held back for review in {label}.",
                     level="warn", client=client.slug, period=period)
                set_setting(session, key, "1")
        if not plan.billable:
            key = f"billing_nothing:{client.id}:{period}"
            if not get_setting(session, key):
                favours = len(plan.goodwill)
                emit(session, "billing_nothing", f"Nothing to bill for {client.name} in {label}. "
                     f"{favours} favour{'s' if favours != 1 else ''} given.", client=client.slug, period=period)
                set_setting(session, key, "1")
            return {"status": "nothing_to_bill"}

        invoice = claim_invoice_slot(session, client, period)
        if invoice is None:
            return {"status": "already_invoiced"}

        notes: list[str] = []
        lines: list[InvoiceLine] = []
        try:
            configure()
            customer_id = _ensure_customer(session, client)
            invoice.stripe_customer_id = customer_id
            proof_url = f"{settings.public_base_url}/proof/{invoice.proof_token}"
            s_inv = _create_stripe_invoice(customer_id, invoice, terms.payment_terms_days, proof_url, notes)
            invoice.stripe_invoice_id = s_inv.id
            session.add(invoice)
            session.commit()

            footer_lines: list[str] = []
            for line in plan.billable + plan.goodwill:
                try:
                    item = stripe.InvoiceItem.create(
                        customer=customer_id, invoice=s_inv.id, currency="gbp", amount=line.amount_pence,
                        description=line.description, metadata={"tab_decision_id": str(line.decision_id)},
                        idempotency_key=f"tab-ii-{invoice.proof_token}-{line.decision_id}",
                    )
                    item_id = item.id
                except stripe.InvalidRequestError as exc:
                    if not line.is_goodwill:
                        raise
                    notes.append(f"Stripe rejected a £0 line, listed in the footer instead: {exc.user_message or exc}")
                    footer_lines.append(line.description)
                    item_id = None
                lines.append(InvoiceLine(invoice_id=invoice.id, decision_id=line.decision_id, stripe_invoice_item_id=item_id,
                                         description=line.description, amount_pence=line.amount_pence, is_goodwill=line.is_goodwill))
            if footer_lines:
                stripe.Invoice.modify(s_inv.id, footer="On the house this month:\n" + "\n".join(footer_lines))

            finalized = stripe.Invoice.finalize_invoice(s_inv.id)
            invoice.hosted_invoice_url = finalized.hosted_invoice_url
            sent = stripe.Invoice.send_invoice(s_inv.id)
            invoice.status = sent.status if sent.status in ("open", "paid", "void") else "open"
            invoice.total_pence = plan.total_pence
            invoice.goodwill_value_pence = plan.goodwill_value_pence
            if sent.total != plan.total_pence:
                notes.append(f"Stripe total {sent.total} differs from Tab's {plan.total_pence} pence.")
            invoice.notes = notes
            session.add(invoice)
            session.add_all(lines)
            session.commit()
        except Exception as exc:  # noqa: BLE001  (any failure: mark failed, never retry)
            invoice.status = "failed"
            invoice.error = f"{type(exc).__name__}: {getattr(exc, 'user_message', None) or exc}"
            invoice.notes = notes
            session.add(invoice)
            session.add_all(lines)
            session.commit()
            emit(session, "billing_error", f"Could not raise the {client.name} invoice for {label}: {invoice.error}. "
                 "Not retried automatically.", level="error", client=client.slug, invoice_id=invoice.id)
            return {"status": "failed", "invoice_id": invoice.id, "error": invoice.error}

        for n in notes:
            emit(session, "billing_note", f"{client.name} invoice: {n}", level="warn", client=client.slug, invoice_id=invoice.id)
        emit(session, "invoice_raised",
             f"Raised invoice for {client.name}: {format_gbp(invoice.total_pence)}, "
             f"{len(plan.billable)} billable line{'s' if len(plan.billable) != 1 else ''}, "
             f"{len(plan.goodwill)} favour{'s' if len(plan.goodwill) != 1 else ''}",
             client=client.slug, invoice_id=invoice.id, stripe_invoice_id=invoice.stripe_invoice_id, period=period)
        return {"status": "raised", "invoice_id": invoice.id, "billable": len(plan.billable), "goodwill": len(plan.goodwill)}


def periods_ready_to_bill(session: Session, client: Client, invoice_day: int) -> list[str]:
    from app.agent.pipeline import active_periods

    now = get_now(session)
    decided = {d.period for d, r in session.exec(
        select(Decision, Request).where(Decision.request_id == Request.id, Request.client_id == client.id)).all()}
    invoiced = {i.period for i in session.exec(select(Invoice).where(Invoice.client_id == client.id)).all()}
    return sorted(p for p in decided & set(active_periods(session))
                  if p not in invoiced and is_period_closed_for_billing(p, now, invoice_day))


async def run_billing_job(session: Session) -> list[dict]:
    status = stripe_key_status()
    results: list[dict] = []
    for client in session.exec(select(Client).order_by(Client.id)).all():
        try:
            terms = load_terms(session, client)
        except TermsIncomplete:
            continue
        for period in periods_ready_to_bill(session, client, terms.invoice_day_of_month):
            if not status.ok:
                key = f"billing_disabled_warned:{client.id}:{period}"
                if not get_setting(session, key):
                    emit(session, "stripe_key_missing", f"{period_label(period)} has closed for {client.name}, but {status.message}",
                         level="warn", client=client.slug, period=period)
                    set_setting(session, key, "1")
                continue
            result = await asyncio.to_thread(raise_invoice_sync, client.id, period)
            results.append({"client": client.slug, "period": period, **result})
            if result.get("status") == "raised":
                await _remember_invoice(session, result["invoice_id"], result["billable"], result["goodwill"])
    return results


async def _remember_invoice(session: Session, invoice_id: int, billable: int, goodwill: int) -> None:
    invoice = session.get(Invoice, invoice_id)
    session.refresh(invoice)
    client = session.get(Client, invoice.client_id)
    try:
        await cognee_client.remember([invoice_record(invoice, client, billable, goodwill)], client.cognee_dataset,
                                     ["invoice", client.slug])
        invoice.remembered_at = utcnow()
        session.add(invoice)
        session.commit()
    except Exception as exc:
        emit(session, "memory_error", f"Could not remember invoice {invoice_id}: {type(exc).__name__}: {exc}", level="error")
