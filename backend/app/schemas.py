"""API request bodies and response serializers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.clock import fmt_london
from app.memory.formatting import channel_of
from app.models import Client, ContractTerm, Decision, Dispute, GoodwillRule, Invoice, InvoiceLine, Request, SourceItem, TimeEntry


# ---------- request bodies ----------

class AskBody(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    client_slug: str | None = None


class DisputeBody(BaseModel):
    line_id: int
    message: str = Field(min_length=2, max_length=2000)


class ClockBody(BaseModel):
    now: str | None = Field(None, description="ISO datetime; naive values are Europe/London. null clears the override.")


class SimulateBody(BaseModel):
    client_slug: str
    channel: Literal["slack", "email"]
    text: str = Field(min_length=2, max_length=2000)


class RuleBody(BaseModel):
    text: str | None = Field(None, min_length=5, max_length=1000)
    enabled: bool | None = None


# ---------- serializers ----------

def iso(dt) -> str | None:  # noqa: ANN001
    return dt.isoformat() if dt else None


def client_out(c: Client) -> dict[str, Any]:
    return {"id": c.id, "slug": c.slug, "name": c.name, "contact_name": c.contact_name, "contact_email": c.contact_email,
            "cognee_dataset": c.cognee_dataset, "stripe_customer_id": c.stripe_customer_id}


def term_out(t: ContractTerm) -> dict[str, Any]:
    return {"key": t.key, "clause_ref": t.clause_ref, "value": t.value_json, "source_text": t.source_text, "confidence": t.confidence}


def rule_out(r: GoodwillRule, clients: dict[int, Client]) -> dict[str, Any]:
    return {"id": r.id, "rule_ref": r.rule_ref, "text": r.text, "params": r.params_json, "enabled": r.enabled,
            "parse_status": r.parse_status, "parse_note": r.parse_note,
            "applies_to": "All clients" if r.client_id is None else clients[r.client_id].name}


def source_item_out(i: SourceItem) -> dict[str, Any]:
    return {"id": i.id, "source": i.source, "simulated": i.source == "simulated", "external_id": i.external_id,
            "occurred_at": iso(i.occurred_at), "occurred_local": fmt_london(i.occurred_at), "author": i.author,
            "title": i.title, "channel": channel_of(i), "text": i.text, "raw": i.raw_json, "period": i.period,
            "client_id": i.client_id, "cognee_dataset": i.cognee_dataset, "cognee_node_set": i.cognee_node_set,
            "remembered_at": iso(i.remembered_at), "processed_at": iso(i.processed_at)}


def time_entry_out(t: TimeEntry) -> dict[str, Any]:
    return {"id": t.id, "started_at": iso(t.started_at), "started_local": fmt_london(t.started_at), "minutes": t.minutes,
            "project": t.project, "description": t.description, "request_id": t.request_id,
            "match_confidence": t.match_confidence, "match_reason": t.match_reason, "source_item_id": t.source_item_id}


def decision_out(d: Decision | None) -> dict[str, Any] | None:
    if d is None:
        return None
    return {"id": d.id, "category": d.category, "clause_refs": d.clause_refs, "rule_refs": d.rule_refs,
            "minutes_logged": d.minutes_logged, "minutes_billed": d.minutes_billed, "amount_pence": d.amount_pence,
            "value_pence": d.value_pence, "explanation": d.explanation, "evidence": d.evidence,
            "cognee_query": d.cognee_query, "cognee_context": d.cognee_context, "confidence": d.confidence,
            "counts_towards_allowance": d.counts_towards_allowance, "period": d.period,
            "created_at": iso(d.created_at), "remembered_at": iso(d.remembered_at)}


def request_out(session: Session, r: Request, decisions: dict[int, Decision]) -> dict[str, Any]:
    item = session.get(SourceItem, r.source_item_id)
    entries = session.exec(select(TimeEntry).where(TimeEntry.request_id == r.id)).all()
    return {"id": r.id, "requested_at": iso(r.requested_at), "requested_local": fmt_london(r.requested_at),
            "summary": r.summary, "quote": r.quote, "kind": r.kind, "page_or_asset": r.page_or_asset,
            "revision_round": r.revision_round, "is_future_work": r.is_future_work, "period": r.period,
            "source": {"id": item.id, "source": item.source, "author": item.author, "channel": channel_of(item),
                       "simulated": item.source == "simulated"},
            "time_entries": [time_entry_out(t) for t in entries],
            "meeting_minutes": int((item.raw_json or {}).get("minutes", 0)) if r.kind == "meeting" else None,
            "decision": decision_out(decisions.get(r.id))}


def invoice_out(i: Invoice, client: Client | None = None) -> dict[str, Any]:
    return {"id": i.id, "client_id": i.client_id, "client": client_out(client) if client else None, "period": i.period,
            "stripe_invoice_id": i.stripe_invoice_id, "stripe_customer_id": i.stripe_customer_id, "status": i.status,
            "total_pence": i.total_pence, "goodwill_value_pence": i.goodwill_value_pence,
            "hosted_invoice_url": i.hosted_invoice_url, "proof_token": i.proof_token, "created_at": iso(i.created_at),
            "error": i.error, "notes": i.notes, "remembered_at": iso(i.remembered_at)}


def line_out(line: InvoiceLine) -> dict[str, Any]:
    return {"id": line.id, "decision_id": line.decision_id, "stripe_invoice_item_id": line.stripe_invoice_item_id,
            "description": line.description, "amount_pence": line.amount_pence, "is_goodwill": line.is_goodwill}


def dispute_out(d: Dispute, internal: bool) -> dict[str, Any]:
    out = {"id": d.id, "invoice_line_id": d.invoice_line_id, "message": d.message, "created_at": iso(d.created_at),
           "agent_reply": d.agent_reply, "outcome": d.outcome}
    if internal:
        out.update({"outcome_reason": d.outcome_reason, "evidence": d.evidence, "cognee_context": d.cognee_context,
                    "remembered_at": iso(d.remembered_at)})
    return out
