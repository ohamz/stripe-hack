"""Orchestrates steps 2-6: remember -> terms/rules -> extract -> match time -> decide -> remember decisions.

Deterministic steps (meeting requests from calendar events) run without an LLM key. Everything that needs
the LLM or Cognee is skipped with a clear "LLM key missing" event instead of faking results.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.agent.decide import decide_period
from app.agent.extract import extract_requests, meeting_request
from app.agent.match_time import match_entry, unmatched_entries
from app.agent.terms import TermsIncomplete, extract_contract_terms, load_terms, parse_goodwill_rule, rules_for_client
from app.clock import START_PERIOD_KEY, get_now, get_setting, period_of
from app.config import llm_key_status
from app.events import emit
from app.memory import cognee_client
from app.memory.formatting import decision_record, source_item_record
from app.models import Client, ContractTerm, Decision, GoodwillRule, Request, SourceItem, utcnow

MESSAGE_SOURCES = ("slack", "email", "simulated")
_pipeline_lock = asyncio.Lock()


@dataclass
class PipelineReport:
    remembered: dict[str, int] = field(default_factory=dict)
    remember_seconds: float = 0.0
    requests_created: int = 0
    time_entries_matched: int = 0
    decisions_made: int = 0
    skipped_reason: str | None = None
    errors: list[str] = field(default_factory=list)


def active_periods(session: Session) -> list[str]:
    """Periods Tab decides and bills: from the start period up to the current one. Earlier items are memory only."""
    now_period = period_of(get_now(session))
    start = get_setting(session, START_PERIOD_KEY)
    periods = {p for p in session.exec(select(SourceItem.period)).all()}
    return sorted(p for p in periods if p <= now_period and (start is None or p >= start))


def _clients(session: Session) -> list[Client]:
    return session.exec(select(Client).order_by(Client.id)).all()


def create_meeting_requests(session: Session, periods: list[str]) -> int:
    """Calendar events -> one meeting request each (no LLM). Also marks non-message items as processed."""
    created = 0
    items = session.exec(select(SourceItem).where(SourceItem.processed_at == None)).all()  # noqa: E711
    for item in items:
        if item.source == "calendar" and item.client_id and item.period in periods:
            client = session.get(Client, item.client_id)
            session.add(meeting_request(item, client))
            item.processed_at = utcnow()
            created += 1
        elif item.source in ("timelog", "contract", "rules") or item.client_id is None:
            item.processed_at = utcnow()
        elif item.period not in periods and item.period < max(periods, default=""):
            item.processed_at = utcnow()  # history: remembered, never decided or billed
            item.raw_json = {**(item.raw_json or {}), "tab_note": "history: memory only"}
        session.add(item)
    session.commit()
    return created


async def remember_source_items(session: Session, report: PipelineReport) -> None:
    pending = session.exec(
        select(SourceItem).where(SourceItem.remembered_at == None, SourceItem.client_id != None)  # noqa: E711
    ).all()
    groups: dict[tuple[int, str], list[SourceItem]] = defaultdict(list)
    for item in pending:
        groups[(item.client_id, item.cognee_node_set[0] if item.cognee_node_set else item.source)].append(item)
    for (client_id, node), items in groups.items():
        client = session.get(Client, client_id)
        records = [source_item_record(i, client.name) for i in sorted(items, key=lambda i: i.occurred_at)]
        started = time.monotonic()
        result = await cognee_client.remember(records, client.cognee_dataset, [node, client.slug])
        report.remember_seconds += time.monotonic() - started
        now = utcnow()
        for i in items:
            i.remembered_at = now
            session.add(i)
        session.commit()
        report.remembered[f"{client.slug}/{node}"] = len(items)
        emit(session, "remembered", f"Remembered {len(items)} {node} record(s) for {client.name}.",
             client=client.slug, node_set=[node, client.slug], dataset=client.cognee_dataset, result=result)


async def ensure_terms_and_rules(session: Session) -> None:
    for client in _clients(session):
        has_terms = session.exec(select(ContractTerm).where(ContractTerm.client_id == client.id)).first()
        if has_terms is None:
            try:
                await extract_contract_terms(session, client)
            except TermsIncomplete:
                pass  # already reported as an error event; decisions for this client stay on hold
    for rule in session.exec(select(GoodwillRule).where(GoodwillRule.parse_status == "pending")).all():
        await parse_goodwill_rule(session, rule)


async def extract_pending(session: Session, periods: list[str], report: PipelineReport) -> None:
    items = session.exec(
        select(SourceItem).where(SourceItem.processed_at == None, SourceItem.client_id != None)  # noqa: E711
    ).all()
    for item in sorted(items, key=lambda i: i.occurred_at):
        if item.source not in MESSAGE_SOURCES or item.period not in periods:
            continue
        client = session.get(Client, item.client_id)
        try:
            requests = await extract_requests(session, item, client)
        except Exception as exc:
            report.errors.append(f"extract {item.source}:{item.external_id}: {exc}")
            emit(session, "extract_error", f"Could not read a {item.source} message from {client.name}: {exc}",
                 level="error", client=client.slug, source_item_id=item.id)
            continue
        item.processed_at = utcnow()
        session.add(item)
        session.commit()
        report.requests_created += len(requests)
        if requests:
            emit(session, "requests_found", f"{client.name}: found {len(requests)} request(s) in a {item.source} message.",
                 client=client.slug, source_item_id=item.id, request_ids=[r.id for r in requests])


async def match_pending(session: Session, periods: list[str], report: PipelineReport) -> None:
    for client in _clients(session):
        requests = session.exec(select(Request).where(Request.client_id == client.id, Request.period.in_(periods))).all()
        for entry in unmatched_entries(session, client, periods):
            try:
                await match_entry(session, entry, client, requests)
                report.time_entries_matched += entry.request_id is not None
            except Exception as exc:
                report.errors.append(f"match time entry {entry.id}: {exc}")
                emit(session, "match_error", f"Could not match a time entry for {client.name}: {exc}", level="error",
                     client=client.slug, time_entry_id=entry.id)


async def decide_pending(session: Session, periods: list[str], report: PipelineReport) -> None:
    for client in _clients(session):
        try:
            terms = load_terms(session, client)
        except TermsIncomplete as exc:
            emit(session, "decisions_on_hold", f"Decisions for {client.name} are on hold: {exc}", level="warn", client=client.slug)
            continue
        rules = rules_for_client(session, client)
        for period in periods:
            try:
                made = await decide_period(session, client, period, terms, rules)
                report.decisions_made += len(made)
            except Exception as exc:
                report.errors.append(f"decide {client.slug} {period}: {exc}")
                emit(session, "decide_error", f"Stopped deciding {client.name} {period}: {type(exc).__name__}: {exc}",
                     level="error", client=client.slug)


async def remember_decisions(session: Session) -> None:
    pending = session.exec(select(Decision).where(Decision.remembered_at == None)).all()  # noqa: E711
    by_client: dict[int, list[str]] = defaultdict(list)
    rows: dict[int, list[Decision]] = defaultdict(list)
    for d in pending:
        req = session.get(Request, d.request_id)
        item = session.get(SourceItem, req.source_item_id)
        client = session.get(Client, req.client_id)
        by_client[client.id].append(decision_record(d, req, item, client))
        rows[client.id].append(d)
    for client_id, records in by_client.items():
        client = session.get(Client, client_id)
        await cognee_client.remember(records, client.cognee_dataset, ["decision", client.slug])
        now = utcnow()
        for d in rows[client_id]:
            d.remembered_at = now
            session.add(d)
        session.commit()
        emit(session, "remembered", f"Wrote {len(records)} decision(s) for {client.name} back to memory.",
             client=client.slug, node_set=["decision", client.slug])


async def run_pipeline(session: Session, reason: str = "") -> PipelineReport:
    async with _pipeline_lock:
        report = PipelineReport()
        periods = active_periods(session)
        report.requests_created += create_meeting_requests(session, periods)
        status = llm_key_status()
        if not status.ok:
            report.skipped_reason = status.message
            emit(session, "llm_key_missing", f"{status.message}. Memory, request extraction and decisions are paused.",
                 level="warn", reason=reason)
            return report
        try:
            await remember_source_items(session, report)
            await ensure_terms_and_rules(session)
            await extract_pending(session, periods, report)
            await match_pending(session, periods, report)
            await decide_pending(session, periods, report)
            await remember_decisions(session)
        except cognee_client.LLMKeyMissing as exc:
            report.skipped_reason = str(exc)
        except Exception as exc:
            report.errors.append(f"{type(exc).__name__}: {exc}")
            emit(session, "pipeline_error", f"Pipeline stopped: {type(exc).__name__}: {exc}", level="error", reason=reason)
        return report


async def redecide_open_period(session: Session, period: str) -> int:
    """After a goodwill rule edit: drop decisions for an un-invoiced period and decide again."""
    from app.models import Invoice

    invoiced = {i.client_id for i in session.exec(select(Invoice).where(Invoice.period == period)).all()}
    dropped = 0
    for d in session.exec(select(Decision).where(Decision.period == period)).all():
        req = session.get(Request, d.request_id)
        if req.client_id in invoiced:
            continue
        session.delete(d)
        dropped += 1
    session.commit()
    return dropped
