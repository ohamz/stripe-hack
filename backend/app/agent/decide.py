"""Step 5: decide (PLAN.md 8.3). Order matters:

1. no matched time and not a meeting -> no_work_logged
2. meeting -> deterministic count/length check
3. scope check (Cognee recall + LLM); confidence < 0.7 -> needs_review; in scope -> included
4. goodwill rules (deterministic, out-of-scope only)
5. otherwise billable

Money maths is deterministic (app.money), never done by the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.agent.llm import structured
from app.agent.terms import Terms
from app.clock import LONDON, fmt_day, fmt_london
from app.events import emit
from app.memory.cognee_client import CONTEXT_LIMIT, recall
from app.memory.formatting import channel_of
from app.models import Client, Decision, GoodwillRule, Request, SourceItem, TimeEntry
from app.money import billed_minutes, format_gbp, format_rate, value_pence

INCLUDED, GOODWILL, BILLABLE, NEEDS_REVIEW, NO_WORK = "included", "goodwill", "billable", "needs_review", "no_work_logged"
CATEGORY_LABELS = {
    INCLUDED: "Included",
    GOODWILL: "On the house",
    BILLABLE: "Billable",
    NEEDS_REVIEW: "Needs review",
    NO_WORK: "No time logged",
}
MIN_CONFIDENCE = 0.7


# ---------- deterministic pieces (unit tested) ----------

@dataclass
class Verdict:
    category: str
    minutes_logged: int
    billable_minutes: int = 0  # minutes the money maths applies to (all of them, or a meeting's overrun)
    clause_refs: list[str] = field(default_factory=list)
    rule_refs: list[str] = field(default_factory=list)
    counts_towards_allowance: bool = False
    confidence: float = 1.0
    facts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Money:
    minutes_billed: int
    amount_pence: int
    value_pence: int


def money_for(verdict: Verdict, increment_minutes: int, hourly_rate_pence: int) -> Money:
    if verdict.category in (BILLABLE, GOODWILL):
        mb = billed_minutes(verdict.billable_minutes, increment_minutes)
        value = value_pence(mb, hourly_rate_pence)
        return Money(mb, value if verdict.category == BILLABLE else 0, value)
    return Money(0, 0, 0)


def meeting_verdict(meeting_number: int, duration: int, meetings_per_month: int, meeting_max_minutes: int,
                    included_ref: str | None, extra_ref: str | None) -> Verdict:
    """Meeting n of the month: included if within count and length; else billable (whole, or only the overrun)."""
    if meeting_number > meetings_per_month:
        return Verdict(BILLABLE, duration, duration, [r for r in [extra_ref] if r],
                       facts=[f"meeting {meeting_number} this month; the contract includes {meetings_per_month}, so the whole meeting is billable"])
    if duration > meeting_max_minutes:
        return Verdict(BILLABLE, duration, duration - meeting_max_minutes, [r for r in [extra_ref] if r],
                       facts=[f"meeting {meeting_number} of {meetings_per_month}, but {duration} min long; only the "
                              f"{duration - meeting_max_minutes} min beyond {meeting_max_minutes} min are billable"])
    return Verdict(INCLUDED, duration, 0, [r for r in [included_ref] if r],
                   facts=[f"meeting {meeting_number} of {meetings_per_month} included this month, {duration} min (limit {meeting_max_minutes} min)"])


@dataclass(frozen=True)
class RuleView:
    rule_ref: str
    params: dict


@dataclass(frozen=True)
class GoodwillOutcome:
    is_goodwill: bool
    rule_ref: str | None = None
    counts_towards_allowance: bool = False
    exhausted_rule_ref: str | None = None
    note: str = ""


def goodwill_outcome(minutes_logged: int, kind: str, is_typo_fix: bool, rules: list[RuleView], favours_used: int) -> GoodwillOutcome:
    """Apply goodwill rules to an out-of-scope request. Always-free kinds first, then the favour allowance."""
    for r in rules:
        p = r.params
        if p.get("type") == "always_free_kind" and ((p.get("kind") == "typo_fix" and is_typo_fix) or p.get("kind") == kind):
            return GoodwillOutcome(True, r.rule_ref, bool(p.get("counts_towards_allowance")),
                                   note=f"{p.get('kind')} is always free under {r.rule_ref}"
                                        + ("" if p.get("counts_towards_allowance") else " and doesn't use the favour allowance"))
    exhausted = None
    for r in rules:
        p = r.params
        if p.get("type") != "small_favour":
            continue
        if minutes_logged < p["max_minutes_exclusive"]:
            if favours_used < p["max_per_month"]:
                return GoodwillOutcome(True, r.rule_ref, True,
                                       note=f"favour {favours_used + 1} of {p['max_per_month']} this month under {r.rule_ref}")
            exhausted = exhausted or r.rule_ref
    if exhausted:
        return GoodwillOutcome(False, exhausted_rule_ref=exhausted, note=f"the {exhausted} favour allowance for this month is used up")
    return GoodwillOutcome(False)


def favours_used_before(decisions: list[tuple[Request, Decision]], before: Request) -> int:
    """Goodwill decisions that count towards the allowance, for requests dated before this one (same client, period)."""
    return sum(
        1 for req, dec in decisions
        if dec.category == GOODWILL and dec.counts_towards_allowance
        and req.client_id == before.client_id and req.period == before.period
        and (req.requested_at, req.id) < (before.requested_at, before.id or 0)
    )


def meeting_number(meetings: list[Request], req: Request) -> int:
    ordered = sorted(meetings, key=lambda r: (r.requested_at, r.id or 0))
    return [m.id for m in ordered].index(req.id) + 1


def bug_fix_window(terms: Terms) -> tuple[date, date]:
    delivered = date.fromisoformat(terms.delivery_date)
    return delivered, delivered + timedelta(days=terms.bug_fix_window_days)


# ---------- LLM scope check ----------

class ScopeCheck(BaseModel):
    in_scope: bool
    clause_refs: list[str] = Field(description="Clause numbers that decide it")
    revision_round: int | None = Field(None, description="For revisions: which round this is for that page (1-based), else null")
    is_typo_fix: bool
    reasoning: str = Field(description="One or two sentences")
    confidence: float = Field(ge=0, le=1)


SCOPE_PROMPT = """You check whether a client's request is covered by a freelancer's fixed-scope contract.
Decide only scope. Do not consider favours, goodwill or whether the freelancer wants to charge.
- in_scope is true only if a contract clause includes this work at no extra charge (a listed page,
  an included revision round, a bug fix inside the bug-fix window, ...).
- Revision rounds: count the earlier rounds for the same page or deliverable in the history, including earlier
  months. revision_round is that count plus one. If it is more than the included rounds, it is out of scope.
  A small content update to a delivered item (for example changing a price) is not a revision round.
- is_typo_fix is true only if the request is to correct a spelling mistake.
- clause_refs: the clause numbers that decide it. For out-of-scope work include the clause that makes it billable.
- Use only the contract, the facts and the memory given. If they don't settle it, give a confidence below 0.7."""


class Explanation(BaseModel):
    explanation: str


EXPLAIN_PROMPT = """Write 2 or 3 short, plain sentences explaining a billing decision, for the freelancer and the client.
Start with the verdict label. Use only the facts given: do not add any fact, number, date, amount or clause that
is not in the input."""


async def scope_check(client: Client, req: Request, item: SourceItem, terms: Terms) -> tuple[ScopeCheck, str, str]:
    day = fmt_day(req.requested_at)
    queries = []
    scope = await recall(
        f"Is this covered by the contract: '{req.summary}'? Quote the clause numbers.",
        datasets=[client.cognee_dataset], query_type="GRAPH_COMPLETION", node_name=["contract"],
    )
    queries.append(scope)
    if req.kind == "revision":
        page = req.page_or_asset or req.summary
        history = await recall(
            f"How many revision rounds has {page} had before {day} {req.requested_at.astimezone(LONDON).year}? List each with date.",
            datasets=[client.cognee_dataset], query_type="GRAPH_COMPLETION",
        )
        queries.append(history)
    delivered, window_end = bug_fix_window(terms)
    req_day = req.requested_at.astimezone(LONDON).date()
    clause_lines = "\n".join(f"{k} {v}" for k, v in terms.clauses.items())
    terms_lines = "\n".join(f"- {k} = {terms.values[k]} (clause {terms.refs.get(k)})" for k in sorted(terms.values))
    memory = "\n\n".join(f"Q: {q.query}\nA: {q.answer}\n{q.evidence_block}" for q in queries)
    text = (
        f"Client: {client.name}\n"
        f"REQUEST: {req.summary}\nKind: {req.kind}\nPage or asset: {req.page_or_asset or 'n/a'}\n"
        f"Requested: {fmt_london(req.requested_at)} via {item.source} ({channel_of(item)}) by {item.author}\n"
        f"Client's words: \"{req.quote}\"\n\n"
        f"FACTS (computed):\n- Delivery date {delivered.isoformat()}; bug fixes included until {window_end.isoformat()}.\n"
        f"- Request date {req_day.isoformat()} is {'inside' if req_day <= window_end else 'outside'} the bug-fix window.\n\n"
        f"CONTRACT CLAUSES:\n{clause_lines}\n\nCONTRACT TERMS:\n{terms_lines}\n\nWHAT MEMORY RECALLED:\n{memory}"
    )
    check = await structured(SCOPE_PROMPT, text, ScopeCheck)
    query_log = "\n".join(f"[{q.query_type}{' node_name=' + str(q.node_name) if q.node_name else ''}] {q.query}" for q in queries)
    context = "\n\n".join(f"Q: {q.query}\n{q.context}" for q in queries)[:CONTEXT_LIMIT]
    return check, query_log, context


def verdict_from_scope(check: ScopeCheck, req: Request, minutes_logged: int, terms: Terms,
                       rules: list[RuleView], favours_used: int) -> Verdict:
    """Deterministic part after the LLM scope check: confidence gate, consistency guards, goodwill, billable."""
    known = set(terms.clauses)
    refs = [r.strip() for r in check.clause_refs if r.strip()]
    unknown = [r for r in refs if known and r not in known]
    refs = [r for r in refs if not known or r in known]
    facts = [f"scope check: {check.reasoning}"]
    if check.revision_round:
        facts.append(f"revision round {check.revision_round} for {req.page_or_asset or 'this item'}; "
                     f"{terms.revision_rounds_per_page} rounds per page are included")
    if check.confidence < MIN_CONFIDENCE:
        return Verdict(NEEDS_REVIEW, minutes_logged, clause_refs=refs, confidence=check.confidence,
                       facts=facts + [f"confidence {check.confidence:.2f} is below {MIN_CONFIDENCE}, so a human should check it"])
    if unknown:
        facts.append(f"ignored clause numbers not in the contract: {', '.join(unknown)}")
    if check.in_scope and check.revision_round and check.revision_round > terms.revision_rounds_per_page:
        return Verdict(NEEDS_REVIEW, minutes_logged, clause_refs=refs, confidence=check.confidence,
                       facts=facts + ["the scope check said 'in scope' but counted more revision rounds than the contract includes"])
    if not refs:
        return Verdict(NEEDS_REVIEW, minutes_logged, confidence=check.confidence,
                       facts=facts + ["no valid contract clause was cited"])
    if check.in_scope:
        return Verdict(INCLUDED, minutes_logged, 0, refs, confidence=check.confidence, facts=facts)
    gw = goodwill_outcome(minutes_logged, req.kind, check.is_typo_fix, rules, favours_used)
    if gw.is_goodwill:
        return Verdict(GOODWILL, minutes_logged, minutes_logged, refs, [gw.rule_ref], gw.counts_towards_allowance,
                       check.confidence, facts + [gw.note])
    rule_refs = [gw.exhausted_rule_ref] if gw.exhausted_rule_ref else []
    return Verdict(BILLABLE, minutes_logged, minutes_logged, refs, rule_refs, False, check.confidence,
                   facts + ([gw.note] if gw.note else []))


# ---------- orchestration ----------

def _evidence(item: SourceItem, entries: list[TimeEntry], refs: list[str], terms: Terms,
              rule_rows: dict[str, GoodwillRule], rule_refs: list[str]) -> list[dict[str, Any]]:
    ev: list[dict[str, Any]] = [{
        "type": "source_item", "id": item.id,
        "label": f"{item.source.capitalize()} from {item.author}, {fmt_london(item.occurred_at)}",
    }]
    for te in entries:
        ev.append({"type": "time_entry", "id": te.id, "label": f"{te.minutes} min logged: {te.description}"})
    for ref in refs:
        ev.append({"type": "clause", "id": ref, "label": f"Clause {ref}: {terms.clauses.get(ref, '')}"})
    for ref in rule_refs:
        rule = rule_rows.get(ref)
        ev.append({"type": "rule", "id": rule.id if rule else ref, "label": f"{ref}: {rule.text if rule else ''}"})
    return ev


async def _explain(client: Client, req: Request, item: SourceItem, verdict: Verdict, money: Money, terms: Terms,
                   rule_rows: dict[str, GoodwillRule]) -> str:
    clause_text = "\n".join(f"- clause {r}: {terms.clauses.get(r, '')}" for r in verdict.clause_refs) or "- none"
    rule_text = "\n".join(f"- {r}: {rule_rows[r].text}" for r in verdict.rule_refs if r in rule_rows) or "- none"
    facts = "\n".join(f"- {f}" for f in verdict.facts) or "- none"
    text = (
        f"Verdict label: {CATEGORY_LABELS[verdict.category]}\n"
        f"Client: {client.name} (contact {client.contact_name})\n"
        f"Request: {req.summary}\nAsked on {fmt_day(req.requested_at)} via {item.source} by {item.author}: \"{req.quote}\"\n"
        f"Minutes logged: {verdict.minutes_logged}\nMinutes billed: {money.minutes_billed}\n"
        f"Amount charged: {format_gbp(money.amount_pence)}\nValue of the work: {format_gbp(money.value_pence)}\n"
        f"Rate: {format_rate(terms.hourly_rate_pence)} (clause {terms.ref('hourly_rate_pence')}), "
        f"billed in {terms.billing_increment_minutes}-minute increments (clause {terms.ref('billing_increment_minutes')})\n"
        f"Contract clauses:\n{clause_text}\nGoodwill rules:\n{rule_text}\nOther facts:\n{facts}"
    )
    out = await structured(EXPLAIN_PROMPT, text, Explanation)
    return out.explanation.strip()


async def decide_request(session: Session, client: Client, req: Request, terms: Terms, rules: list[GoodwillRule],
                         all_requests: list[Request], decided: list[tuple[Request, Decision]]) -> Decision:
    item = session.get(SourceItem, req.source_item_id)
    entries = session.exec(select(TimeEntry).where(TimeEntry.request_id == req.id)).all()
    rule_rows = {r.rule_ref: r for r in rules}
    rule_views = [RuleView(r.rule_ref, r.params_json) for r in rules]
    cognee_query, cognee_context = "", ""

    if req.kind == "meeting":
        duration = int((item.raw_json or {}).get("minutes", 0))
        n = meeting_number([r for r in all_requests if r.kind == "meeting"], req)
        verdict = meeting_verdict(n, duration, terms.meetings_per_month, terms.meeting_max_minutes,
                                  terms.ref("meetings_per_month"), terms.ref("extra_meetings_clause"))
    elif not entries:
        verdict = Verdict(NO_WORK, 0, facts=["no time entry was matched to this request, so nothing is billed"]
                          + (["the client asked for this as future work"] if req.is_future_work else []))
    else:
        minutes = sum(te.minutes for te in entries)
        check, cognee_query, cognee_context = await scope_check(client, req, item, terms)
        if check.revision_round:
            req.revision_round = check.revision_round
            session.add(req)
        verdict = verdict_from_scope(check, req, minutes, terms, rule_views, favours_used_before(decided, req))

    money = money_for(verdict, terms.billing_increment_minutes, terms.hourly_rate_pence)
    if verdict.category in (BILLABLE, GOODWILL):
        rate_ref = terms.ref("hourly_rate_pence")
        if rate_ref and rate_ref not in verdict.clause_refs:
            verdict.clause_refs.append(rate_ref)
    explanation = await _explain(client, req, item, verdict, money, terms, rule_rows)
    decision = Decision(
        request_id=req.id,
        category=verdict.category,
        clause_refs=verdict.clause_refs,
        rule_refs=verdict.rule_refs,
        minutes_logged=verdict.minutes_logged,
        minutes_billed=money.minutes_billed,
        amount_pence=money.amount_pence,
        value_pence=money.value_pence,
        explanation=explanation,
        evidence=_evidence(item, entries, verdict.clause_refs, terms, rule_rows, verdict.rule_refs),
        cognee_query=cognee_query,
        cognee_context=cognee_context,
        confidence=verdict.confidence,
        counts_towards_allowance=verdict.counts_towards_allowance,
        period=req.period,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    amount = f" {format_gbp(money.amount_pence)}" if verdict.category == BILLABLE else (
        f" (worth {format_gbp(money.value_pence)})" if verdict.category == GOODWILL else "")
    emit(session, "decision", f"{client.name}: {req.summary} → {CATEGORY_LABELS[verdict.category]}{amount}",
         level="warn" if verdict.category == NEEDS_REVIEW else "info",
         client=client.slug, decision_id=decision.id, request_id=req.id, category=verdict.category)
    return decision


async def decide_period(session: Session, client: Client, period: str, terms: Terms, rules: list[GoodwillRule]) -> list[Decision]:
    requests = session.exec(
        select(Request).where(Request.client_id == client.id, Request.period == period)
    ).all()
    requests = sorted(requests, key=lambda r: (r.requested_at, r.id))
    existing = {d.request_id: d for d in session.exec(select(Decision).where(Decision.period == period)).all()}
    decided: list[tuple[Request, Decision]] = [(r, existing[r.id]) for r in requests if r.id in existing]
    made: list[Decision] = []
    for req in requests:
        if req.id in existing:
            continue
        decision = await decide_request(session, client, req, terms, rules, requests, decided)
        decided.append((req, decision))
        made.append(decision)
    return made
