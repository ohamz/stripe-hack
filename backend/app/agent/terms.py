"""Contract terms extraction and goodwill rule parsing (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.agent.llm import structured
from app.connectors.contract import parse_clauses
from app.events import emit
from app.memory.cognee_client import recall
from app.models import Client, ContractTerm, GoodwillRule, SourceItem

REQUIRED_KEYS = [
    "included_pages",
    "revision_rounds_per_page",
    "bug_fix_window_days",
    "delivery_date",
    "meetings_per_month",
    "meeting_max_minutes",
    "hourly_rate_pence",
    "billing_increment_minutes",
    "invoice_day_of_month",
    "payment_terms_days",
    "out_of_scope_examples",
]
# Not in PLAN.md's required list: the clause numbers that make extra work billable. Extracted (not
# hardcoded) so meeting and revision decisions can cite the right clause for any contract.
CLAUSE_ONLY_KEYS = ["out_of_scope_clause", "extra_revisions_clause", "extra_meetings_clause"]

INT_KEYS = {
    "revision_rounds_per_page", "bug_fix_window_days", "meetings_per_month", "meeting_max_minutes",
    "hourly_rate_pence", "billing_increment_minutes", "invoice_day_of_month", "payment_terms_days",
}
LIST_KEYS = {"included_pages", "out_of_scope_examples"}

REQUEST_KINDS = ["design_change", "new_deliverable", "revision", "bug_fix", "typo_fix", "meeting", "other"]


class TermsIncomplete(RuntimeError):
    pass


# ---------- LLM output schemas ----------

class _Base(BaseModel):
    clause_ref: str = Field(description="Clause number in the contract, e.g. '2.1'")
    source_text: str = Field(description="The clause text, quoted from the contract")
    confidence: float = Field(ge=0, le=1)


class IntTerm(_Base):
    value: int


class ListTerm(_Base):
    value: list[str]


class DateTerm(_Base):
    value: str = Field(description="ISO date YYYY-MM-DD")


class ClauseOnly(_Base):
    pass


class ExtractedTerms(BaseModel):
    included_pages: ListTerm | None = Field(None, description="Pages or deliverables included in the fixed scope")
    revision_rounds_per_page: IntTerm | None = Field(None, description="Revision rounds included per page or deliverable")
    bug_fix_window_days: IntTerm | None = Field(None, description="Days after the delivery date during which bug/error fixes are included")
    delivery_date: DateTerm | None = None
    meetings_per_month: IntTerm | None = None
    meeting_max_minutes: IntTerm | None = Field(None, description="Maximum included length of each meeting, in minutes")
    hourly_rate_pence: IntTerm | None = Field(None, description="Hourly rate for out-of-scope work, in pence (GBP 50 = 5000)")
    billing_increment_minutes: IntTerm | None = None
    invoice_day_of_month: IntTerm | None = None
    payment_terms_days: IntTerm | None = None
    out_of_scope_examples: ListTerm | None = Field(None, description="Examples of out-of-scope work named in the contract; empty list if none")
    out_of_scope_clause: ClauseOnly | None = Field(None, description="The clause saying work outside the scope is billed")
    extra_revisions_clause: ClauseOnly | None = Field(None, description="The clause saying additional revision rounds are billed")
    extra_meetings_clause: ClauseOnly | None = Field(None, description="The clause saying additional or longer meetings are billed")


TERMS_PROMPT = """You extract contract terms for a freelancer's billing assistant.
Use only what the contract says. Never invent a value. If a term is not in the contract, return null for it.
Every term must cite the clause number it comes from and quote that clause's text.
Money is in pence (GBP 50 per hour -> 5000). Dates are YYYY-MM-DD. Durations are minutes or days as named.
Numbers written as words with digits in brackets, like "two (2)", mean that number."""


@dataclass
class Terms:
    values: dict[str, Any]
    refs: dict[str, str]
    clauses: dict[str, str]

    def __getattr__(self, key: str) -> Any:
        values = self.__dict__.get("values", {})
        if key in values:
            return values[key]
        raise AttributeError(key)

    def ref(self, key: str) -> str | None:
        return self.refs.get(key)


def validate_terms(extracted: ExtractedTerms, clauses: dict[str, str]) -> tuple[dict[str, dict], list[str], list[str]]:
    """Deterministic checks on LLM output. Returns (rows by key, missing keys, warnings)."""
    rows: dict[str, dict] = {}
    missing: list[str] = []
    warnings: list[str] = []
    for key in REQUIRED_KEYS + CLAUSE_ONLY_KEYS:
        term = getattr(extracted, key)
        if term is None:
            missing.append(key)
            continue
        value = getattr(term, "value", None)
        if key in INT_KEYS and (not isinstance(value, int) or value <= 0):
            missing.append(key)
            warnings.append(f"{key}: not a positive whole number ({value!r})")
            continue
        if key == "delivery_date":
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError):
                missing.append(key)
                warnings.append(f"delivery_date: not an ISO date ({value!r})")
                continue
        ref = term.clause_ref.strip()
        confidence = term.confidence
        if clauses and ref not in clauses:
            warnings.append(f"{key}: cited clause {ref} is not in the contract")
            confidence = min(confidence, 0.5)
        rows[key] = {"clause_ref": ref, "value": value, "source_text": term.source_text, "confidence": confidence}
    return rows, [k for k in missing if k in REQUIRED_KEYS + CLAUSE_ONLY_KEYS], warnings


def contract_item(session: Session, client: Client) -> SourceItem | None:
    return session.exec(
        select(SourceItem).where(SourceItem.client_id == client.id, SourceItem.source == "contract")
    ).first()


async def extract_contract_terms(session: Session, client: Client) -> list[ContractTerm]:
    item = contract_item(session, client)
    if item is None:
        raise TermsIncomplete(f"No contract on file for {client.name}")
    clauses = parse_clauses(item.text)
    outcome = await recall(
        "List every numbered clause in the contract with its clause number and full text.",
        datasets=[client.cognee_dataset],
        query_type="RAG_COMPLETION",
        node_name=["contract"],
    )
    text = (
        f"Client: {client.name}\n\nCONTRACT TEXT:\n{item.text}\n\n"
        f"WHAT MEMORY RECALLED ABOUT THE CONTRACT:\n{outcome.answer}"
    )
    extracted = await structured(TERMS_PROMPT, text, ExtractedTerms)
    rows, missing, warnings = validate_terms(extracted, clauses)
    if missing:
        # One retry that names the missing keys. The model must still read them from the contract; nothing is defaulted.
        retry_text = text + (f"\n\nYour previous answer left out: {', '.join(missing)}. Read the contract again and fill them "
                             "in if the contract states them (a list may be empty only if the contract names none).")
        extracted = await structured(TERMS_PROMPT, retry_text, ExtractedTerms)
        rows, missing, warnings = validate_terms(extracted, clauses)
    for w in warnings:
        emit(session, "terms_warning", f"{client.name} contract: {w}", level="warn", client=client.slug)
    if missing:
        emit(session, "terms_incomplete", f"Contract terms missing for {client.name}: {', '.join(missing)}. Decisions are on hold.",
             level="error", client=client.slug, missing=missing, cognee_query=outcome.query, cognee_context=outcome.context)
        raise TermsIncomplete(f"{client.name}: missing contract terms {missing}")
    for old in session.exec(select(ContractTerm).where(ContractTerm.client_id == client.id)).all():
        session.delete(old)
    terms = [
        ContractTerm(client_id=client.id, clause_ref=r["clause_ref"], key=key, value_json=r["value"],
                     source_text=r["source_text"], confidence=r["confidence"])
        for key, r in rows.items()
    ]
    session.add_all(terms)
    session.commit()
    emit(session, "terms_extracted", f"Read the {client.name} contract: {len(terms)} terms with clause references.",
         client=client.slug, cognee_query=outcome.query, cognee_context=outcome.context)
    return terms


def load_terms(session: Session, client: Client) -> Terms:
    rows = session.exec(select(ContractTerm).where(ContractTerm.client_id == client.id)).all()
    values = {r.key: r.value_json for r in rows}
    refs = {r.key: r.clause_ref for r in rows}
    missing = [k for k in REQUIRED_KEYS + CLAUSE_ONLY_KEYS if k not in values]
    if missing:
        raise TermsIncomplete(f"{client.name}: missing contract terms {missing}")
    item = contract_item(session, client)
    return Terms(values=values, refs=refs, clauses=parse_clauses(item.text) if item else {})


# ---------- goodwill rules ----------

class ParsedRule(BaseModel):
    type: Literal["small_favour", "always_free_kind", "not_understood"]
    max_minutes_exclusive: int | None = Field(None, description="small_favour: favours must take strictly fewer minutes than this")
    max_per_month: int | None = Field(None, description="small_favour: how many favours per client per calendar month")
    kind: Literal["design_change", "new_deliverable", "revision", "bug_fix", "typo_fix", "other"] | None = Field(
        None, description="always_free_kind: the kind of request that is always free")
    counts_towards_allowance: bool | None = Field(None, description="always_free_kind: does it use up the small-favour allowance?")
    note: str = Field("", description="One short sentence on how the rule was read")


RULE_PROMPT = """You turn a freelancer's plain-English goodwill rule into parameters. Supported rule types:
1. small_favour: favours that take under N minutes are free, up to M per client per calendar month.
   Return max_minutes_exclusive=N and max_per_month=M.
2. always_free_kind: a kind of request (e.g. typo fixes) is always free. Return kind and
   counts_towards_allowance (false if the rule says it doesn't count towards the favour allowance).
If the rule does not fit one of these exactly, return type "not_understood". Never guess numbers."""


def validate_rule_params(parsed: ParsedRule) -> dict | None:
    """Deterministic validation; anything incomplete is not applied."""
    if parsed.type == "small_favour":
        if isinstance(parsed.max_minutes_exclusive, int) and parsed.max_minutes_exclusive > 0 \
                and isinstance(parsed.max_per_month, int) and parsed.max_per_month > 0:
            return {"type": "small_favour", "max_minutes_exclusive": parsed.max_minutes_exclusive,
                    "max_per_month": parsed.max_per_month}
        return None
    if parsed.type == "always_free_kind":
        if parsed.kind in REQUEST_KINDS and parsed.kind != "meeting" and isinstance(parsed.counts_towards_allowance, bool):
            return {"type": "always_free_kind", "kind": parsed.kind,
                    "counts_towards_allowance": parsed.counts_towards_allowance}
        return None
    return None


async def parse_goodwill_rule(session: Session, rule: GoodwillRule) -> GoodwillRule:
    parsed = await structured(RULE_PROMPT, f"Rule {rule.rule_ref}: {rule.text}", ParsedRule)
    params = validate_rule_params(parsed)
    rule.params_json = params
    rule.parse_status = "parsed" if params else "not_understood"
    rule.parse_note = parsed.note
    session.add(rule)
    session.commit()
    if params is None:
        emit(session, "rule_not_understood", f"Goodwill rule {rule.rule_ref} was not understood and will not be applied.",
             level="warn", rule=rule.rule_ref)
    else:
        emit(session, "rule_parsed", f"Goodwill rule {rule.rule_ref} understood as {params['type']}.", rule=rule.rule_ref, params=params)
    return rule


def rules_for_client(session: Session, client: Client) -> list[GoodwillRule]:
    """Enabled, parsed rules that apply to this client; client-specific rules first."""
    rows = session.exec(select(GoodwillRule).where(GoodwillRule.enabled == True)).all()  # noqa: E712
    applicable = [r for r in rows if r.params_json and (r.client_id is None or r.client_id == client.id)]
    return sorted(applicable, key=lambda r: (r.client_id is None, r.rule_ref))
