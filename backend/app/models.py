"""All tables (PLAN.md section 6). Money is integer pence; timestamps are UTC."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column, DateTime, Text, TypeDecorator, UniqueConstraint
from sqlmodel import Field, SQLModel


class UTCDateTime(TypeDecorator):
    """Stores UTC, always returns timezone-aware UTC datetimes (SQLite drops tzinfo)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime stored; use timezone-aware UTC")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ts(nullable: bool = True, **kw: Any):
    return Field(sa_column=Column(UTCDateTime(), nullable=nullable), **kw)


def _json(default_factory=list):  # noqa: ANN001
    return Field(default_factory=default_factory, sa_column=Column(JSON))


def _json_nullable():
    return Field(default=None, sa_column=Column(JSON, nullable=True))


class Client(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    name: str
    contact_name: str
    contact_email: str
    email_domains: list = _json()
    slack_channels: list = _json()
    slack_user_names: list = _json()
    calendar_match: list = _json()
    timetracker_client: str
    contract_file: str = ""
    cognee_dataset: str
    stripe_customer_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))


class ContractTerm(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    clause_ref: str
    key: str
    value_json: Any = Field(default=None, sa_column=Column(JSON))
    source_text: str = Field(default="", sa_column=Column(Text))
    confidence: float = 0.0


class GoodwillRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    client_id: Optional[int] = Field(default=None, foreign_key="client.id")
    rule_ref: str
    text: str = Field(sa_column=Column(Text))
    params_json: Optional[dict] = _json_nullable()
    enabled: bool = True
    # Not in PLAN.md: lets the UI tell "not understood" apart from "not parsed yet (LLM key missing)".
    parse_status: str = "pending"  # "pending" | "parsed" | "not_understood" | "error"
    parse_note: Optional[str] = None


class SourceItem(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("source", "external_id"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    client_id: Optional[int] = Field(default=None, foreign_key="client.id", index=True)
    source: str  # slack | email | calendar | timelog | contract | rules | simulated
    external_id: str
    occurred_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    author: str = ""
    title: Optional[str] = None
    text: str = Field(default="", sa_column=Column(Text))
    raw_json: dict = _json(dict)
    period: str = Field(index=True)
    cognee_dataset: Optional[str] = None
    cognee_node_set: list = _json()
    remembered_at: Optional[datetime] = _ts()
    processed_at: Optional[datetime] = _ts()


class Request(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    source_item_id: int = Field(foreign_key="sourceitem.id")
    requested_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    summary: str
    quote: str = ""
    kind: str  # design_change | new_deliverable | revision | bug_fix | typo_fix | meeting | other
    page_or_asset: Optional[str] = None
    revision_round: Optional[int] = None
    # Not in PLAN.md's table but in the step-3 output schema.
    is_future_work: bool = False
    period: str = Field(index=True)


class TimeEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_item_id: int = Field(foreign_key="sourceitem.id")
    client_id: Optional[int] = Field(default=None, foreign_key="client.id", index=True)
    started_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    minutes: int
    project: str = ""
    description: str = ""
    request_id: Optional[int] = Field(default=None, foreign_key="request.id")
    match_confidence: Optional[float] = None
    match_reason: Optional[str] = None
    # Not in PLAN.md: marks entries the matcher has looked at, so it doesn't re-ask the LLM.
    matched_at: Optional[datetime] = _ts()


class Decision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    request_id: int = Field(foreign_key="request.id", unique=True)
    category: str  # included | goodwill | billable | needs_review | no_work_logged
    clause_refs: list = _json()
    rule_refs: list = _json()
    minutes_logged: int = 0
    minutes_billed: int = 0
    amount_pence: int = 0
    value_pence: int = 0
    explanation: str = Field(default="", sa_column=Column(Text))
    evidence: list = _json()
    cognee_query: str = Field(default="", sa_column=Column(Text))
    cognee_context: str = Field(default="", sa_column=Column(Text))
    confidence: float = 0.0
    # Not in PLAN.md: does this goodwill decision use up the favour allowance? (G2 typo fixes don't)
    counts_towards_allowance: bool = False
    period: str = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))
    remembered_at: Optional[datetime] = _ts()


class Invoice(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("client_id", "period"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.id")
    period: str
    stripe_invoice_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    status: str = "draft"  # draft | open | paid | void | failed
    total_pence: int = 0
    goodwill_value_pence: int = 0
    hosted_invoice_url: Optional[str] = None
    proof_token: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))
    error: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    # Not in PLAN.md: records Stripe-side fallbacks (custom field skipped, £0 lines moved to footer).
    notes: list = _json()
    remembered_at: Optional[datetime] = _ts()


class InvoiceLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    invoice_id: int = Field(foreign_key="invoice.id", index=True)
    decision_id: int = Field(foreign_key="decision.id")
    stripe_invoice_item_id: Optional[str] = None
    description: str
    amount_pence: int
    is_goodwill: bool = False


class Dispute(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    invoice_line_id: int = Field(foreign_key="invoiceline.id", index=True)
    message: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))
    agent_reply: str = Field(default="", sa_column=Column(Text))
    outcome: str = "escalated"  # upheld | escalated
    evidence: list = _json()
    cognee_context: str = Field(default="", sa_column=Column(Text))
    # Not in PLAN.md: why the outcome was chosen (shown to Maya, not to the client).
    outcome_reason: str = Field(default="", sa_column=Column(Text))
    remembered_at: Optional[datetime] = _ts()


class AgentEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))
    level: str = "info"  # info | warn | error
    type: str
    message: str
    payload_json: dict = _json(dict)


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = Field(default="", sa_column=Column(Text))


__all__ = [
    "AgentEvent", "Client", "ContractTerm", "Decision", "Dispute", "GoodwillRule", "Invoice",
    "InvoiceLine", "Request", "Setting", "SourceItem", "TimeEntry", "UTCDateTime", "date", "utcnow",
]
