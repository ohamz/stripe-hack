"""Explanations from Cognee memory: Ask Tab, dispute replies, health narrative."""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.agent.llm import structured
from app.clock import fmt_day, period_label
from app.events import emit
from app.health import HealthNumbers, unverified_numbers
from app.memory import cognee_client
from app.memory.formatting import dispute_record
from app.models import Client, Decision, Dispute, InvoiceLine, Request, SourceItem, TimeEntry, utcnow
from app.money import format_gbp

log = logging.getLogger("tab")

ESCALATED_REPLY = "Thanks for raising this. Maya will get back to you personally."


def remembered_datasets(session: Session) -> list[str]:
    rows = session.exec(select(SourceItem.cognee_dataset).where(SourceItem.remembered_at != None)).all()  # noqa: E711
    return sorted({r for r in rows if r})


async def ask(session: Session, question: str, client: Client | None) -> dict:
    cognee_client.require_llm()
    datasets = [client.cognee_dataset] if client else remembered_datasets(session)
    if not datasets:
        raise cognee_client.MemoryEmpty("Nothing has been remembered yet. Run the seed first.")
    outcome = await cognee_client.recall(question, datasets=datasets, query_type="GRAPH_COMPLETION")
    emit(session, "ask", f"Answered from memory: \"{question[:80]}\"", client=client.slug if client else None,
         cognee_query=outcome.query, cognee_context=outcome.context, datasets=datasets)
    return outcome.to_dict()


# ---------- disputes ----------

class DisputeAssessment(BaseModel):
    reply: str = Field(description="Polite reply to the client, 3-5 sentences")
    raises_new_fact: bool = Field(description="True if the client's message relies on a fact that is not in the evidence or memory")
    new_fact: str | None = Field(None, description="The fact that is not supported, if any")
    confidence: float = Field(ge=0, le=1)


DISPUTE_PROMPT = """You help a freelancer answer a client who questions one line of an invoice.
Write a polite, short reply that cites the contract clause, the client's own message (with its date and a short quote)
and the hours logged. Use only the evidence and memory given; never invent facts, and never offer a refund, credit or discount.
Also decide whether the client's message relies on a fact that is not supported by the evidence or memory
(for example a phone call or promise that nothing on record mentions). If so, raises_new_fact is true."""


def dispute_preconditions(decision: Decision) -> tuple[bool, list[str]]:
    """PLAN.md 10.3: a clause ref AND a client source item AND a matched time entry."""
    types = {e.get("type") for e in decision.evidence or []}
    missing = []
    if not decision.clause_refs:
        missing.append("no contract clause")
    if "source_item" not in types:
        missing.append("no client message")
    if "time_entry" not in types:
        missing.append("no matched time entry")
    return not missing, missing


async def handle_dispute(session: Session, line: InvoiceLine, message: str, client: Client) -> Dispute:
    decision = session.get(Decision, line.decision_id)
    request = session.get(Request, decision.request_id)
    item = session.get(SourceItem, request.source_item_id)
    entries = session.exec(select(TimeEntry).where(TimeEntry.request_id == request.id)).all()
    dispute = Dispute(invoice_line_id=line.id, message=message, outcome="escalated", agent_reply="",
                      evidence=decision.evidence)
    session.add(dispute)
    session.commit()
    session.refresh(dispute)

    ok, missing = dispute_preconditions(decision)
    try:
        outcome = await cognee_client.recall(
            f"Evidence for invoice line '{line.description}' and the dispute '{message}'",
            datasets=[client.cognee_dataset], query_type="GRAPH_COMPLETION",
        )
        dispute.cognee_context = outcome.context
        evidence_text = (
            f"Invoice line: {line.description} ({format_gbp(line.amount_pence)})\n"
            f"Decision: {decision.category}; clauses {', '.join(decision.clause_refs)}; {decision.explanation}\n"
            f"Client's original message ({item.source}, {fmt_day(item.occurred_at)}, from {item.author}): \"{request.quote}\"\n"
            f"Time logged: " + ("; ".join(f"{te.minutes} min '{te.description}'" for te in entries) or "none") + "\n"
            f"Evidence list: " + "; ".join(e.get("label", "") for e in decision.evidence or []) + "\n\n"
            f"WHAT MEMORY RECALLED:\n{outcome.answer}\n{outcome.evidence_block}\n\n"
            f"CLIENT'S DISPUTE MESSAGE:\n{message}"
        )
        assessment = await structured(DISPUTE_PROMPT, evidence_text, DisputeAssessment)
        if ok and not assessment.raises_new_fact and assessment.confidence >= 0.7:
            dispute.outcome = "upheld"
            dispute.agent_reply = assessment.reply.strip()
            dispute.outcome_reason = "Clause, client message and time entry on record; the dispute raises nothing new."
        else:
            reasons = missing + ([f"the client mentions something not on record: {assessment.new_fact or 'unspecified'}"]
                                 if assessment.raises_new_fact else []) + \
                      ([f"low confidence ({assessment.confidence:.2f})"] if assessment.confidence < 0.7 else [])
            dispute.agent_reply = ESCALATED_REPLY
            dispute.outcome_reason = "Escalated: " + "; ".join(reasons) + f". Draft reply (not sent): {assessment.reply.strip()}"
    except Exception as exc:  # keep the dispute; a human answers it
        dispute.agent_reply = ESCALATED_REPLY
        dispute.outcome_reason = f"Escalated: Tab could not answer automatically ({type(exc).__name__}: {exc})"
    session.add(dispute)
    session.commit()
    emit(session, "dispute", f"{client.name} questioned '{line.description[:60]}': {dispute.outcome}.",
         level="warn" if dispute.outcome == "escalated" else "info", client=client.slug, dispute_id=dispute.id,
         outcome=dispute.outcome, cognee_context=dispute.cognee_context)
    # Remember the dispute (with its outcome) after replying, so the reply isn't delayed by graph building.
    asyncio.get_running_loop().create_task(_remember_dispute(dispute.id, line.description, client.id))
    return dispute


async def _remember_dispute(dispute_id: int, line_description: str, client_id: int) -> None:
    from app.db import session_scope

    with session_scope() as session:
        dispute = session.get(Dispute, dispute_id)
        client = session.get(Client, client_id)
        try:
            await cognee_client.remember([dispute_record(dispute, line_description, client)],
                                         client.cognee_dataset, ["dispute", client.slug])
            dispute.remembered_at = utcnow()
            session.add(dispute)
            session.commit()
        except Exception as exc:
            emit(session, "memory_error", f"Could not remember dispute {dispute_id}: {type(exc).__name__}: {exc}", level="error")


# ---------- health narrative ----------

class Narrative(BaseModel):
    paragraph: str


HEALTH_PROMPT = """Write one short paragraph (3-4 sentences) for a freelancer about one client's month: how much work
was beyond the contract, what kind, the favours given, and one practical recommendation (for example raising the rate
at renewal or agreeing a retainer). You may only use numbers from NUMBERS, written exactly as given (you may round the
percentage to a whole number). Do not mention dates, years or any other number."""


async def health_narrative(session: Session, client: Client, period: str, numbers: HealthNumbers) -> dict:
    cognee_client.require_llm()
    outcome = await cognee_client.recall(
        f"Summarise how often {client.name} asked for work outside the contract this month ({period_label(period)}) and what kind",
        datasets=[client.cognee_dataset], query_type="GRAPH_COMPLETION",
    )
    nums = (
        f"hours total {numbers.hours_total:.2f}; hours in scope {numbers.hours_in_scope:.2f}; hours beyond scope "
        f"{numbers.hours_beyond_scope:.2f}; beyond-scope share {numbers.beyond_scope_share_pct:.1f}%; favours used "
        f"{numbers.favours_used}; extra always-free favours {numbers.favours_free_kind}; amount billed "
        f"{format_gbp(numbers.amount_billed_pence)}; items needing review {numbers.needs_review}; badge {numbers.badge}"
    )
    text = f"Client: {client.name}\nNUMBERS: {nums}\n\nWHAT MEMORY RECALLED:\n{outcome.answer}"
    paragraph, bad = "", []
    for _ in range(2):
        paragraph = (await structured(HEALTH_PROMPT, text, Narrative)).paragraph.strip()
        bad = unverified_numbers(paragraph, numbers)
        if not bad:
            break
        text += f"\n\nYour last draft used numbers that are not in NUMBERS ({', '.join(bad)}). Rewrite without them."
    emit(session, "health", f"Wrote the {period_label(period)} health note for {client.name}.", client=client.slug,
         cognee_query=outcome.query, cognee_context=outcome.context, rejected_numbers=bad)
    if bad:
        return {"paragraph": None, "withheld_reason": f"Narrative withheld: it used numbers not in the report ({', '.join(bad)}).",
                "cognee_query": outcome.query, "cognee_context": outcome.context}
    return {"paragraph": paragraph, "withheld_reason": None, "cognee_query": outcome.query, "cognee_context": outcome.context}
