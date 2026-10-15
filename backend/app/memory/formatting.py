"""Text records written into Cognee (PLAN.md 7.2, exact formats)."""

from __future__ import annotations

from app.clock import fmt_day, fmt_london
from app.money import format_gbp
from app.models import Client, Decision, Dispute, Invoice, Request, SourceItem


def channel_of(item: SourceItem) -> str:
    raw = item.raw_json or {}
    if item.source == "slack":
        return raw.get("channel", "")
    if item.source == "email":
        return item.title or ""
    if item.source == "calendar":
        return item.title or ""
    if item.source == "timelog":
        return raw.get("project", item.title or "")
    if item.source == "simulated":
        return f"{raw.get('channel', 'message')} (Simulated)"
    return item.title or item.source


def source_item_record(item: SourceItem, client_name: str) -> str:
    return (
        f"[SOURCE ITEM {item.source}:{item.external_id}]\n"
        f"Client: {client_name}\n"
        f"Date: {fmt_london(item.occurred_at)} Europe/London\n"
        f"From: {item.author}\n"
        f"Channel: {channel_of(item)}\n"
        f"Text: {item.text}"
    )


def decision_record(decision: Decision, request: Request, item: SourceItem, client: Client) -> str:
    return (
        f"[DECISION decision:{decision.id}]\n"
        f"Client: {client.name}\n"
        f"Request: {request.summary} (requested {fmt_london(request.requested_at)[:10]} via {item.source}:{item.external_id})\n"
        f"Verdict: {decision.category}\n"
        f"Clauses: {', '.join(decision.clause_refs) or 'none'} | Goodwill rules: {', '.join(decision.rule_refs) or 'none'}\n"
        f"Time logged: {decision.minutes_logged} min, billed {decision.minutes_billed} min, "
        f"amount {format_gbp(decision.amount_pence)}, value {format_gbp(decision.value_pence)}\n"
        f"Reason: {decision.explanation}"
    )


def invoice_record(invoice: Invoice, client: Client, billable_lines: int, goodwill_lines: int) -> str:
    return (
        f"[INVOICE invoice:{invoice.id}]\n"
        f"Client: {client.name}\n"
        f"Period: {invoice.period}\n"
        f"Stripe invoice: {invoice.stripe_invoice_id} (status {invoice.status})\n"
        f"Total: {format_gbp(invoice.total_pence)} for {billable_lines} billable lines; "
        f"{goodwill_lines} favours on the house worth {format_gbp(invoice.goodwill_value_pence)}"
    )


def dispute_record(dispute: Dispute, line_description: str, client: Client) -> str:
    return (
        f"[DISPUTE dispute:{dispute.id}]\n"
        f"Client: {client.name}\n"
        f"Date: {fmt_london(dispute.created_at)} Europe/London\n"
        f"Invoice line: {line_description}\n"
        f"Client message: {dispute.message}\n"
        f"Outcome: {dispute.outcome}\n"
        f"Tab reply: {dispute.agent_reply}"
    )


__all__ = ["channel_of", "decision_record", "dispute_record", "fmt_day", "invoice_record", "source_item_record"]
