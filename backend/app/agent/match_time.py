"""Step 4: match time entries to requests (PLAN.md 8.2)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.agent.llm import structured
from app.clock import days_between, fmt_london
from app.events import emit
from app.models import Client, Request, TimeEntry, utcnow

MIN_CONFIDENCE = 0.7
# Time entry date minus request date, in days. PLAN.md says "within -1 to +3 days of the entry date";
# read as: work is logged from 1 day before the request up to 3 days after it (see REPORT.md, Unclear).
WINDOW_MIN_DAYS = -1
WINDOW_MAX_DAYS = 3


class MatchChoice(BaseModel):
    candidate_number: int | None = Field(description="Number of the request this time entry was spent on, or null if none")
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(description="One short sentence")


MATCH_PROMPT = """A freelancer logged a time entry. Decide which client request (if any) the time was spent on.
Return the candidate number, or null if none of them fits. Be strict: the description must clearly be about that request.
Confidence is 0 to 1."""


def candidate_requests(entry: TimeEntry, requests: list[Request]) -> list[Request]:
    """Same client, not meetings, entry date within the window around the request date."""
    out = []
    for r in requests:
        if r.client_id != entry.client_id or r.kind == "meeting":
            continue
        delta = days_between(r.requested_at, entry.started_at)
        if WINDOW_MIN_DAYS <= delta <= WINDOW_MAX_DAYS:
            out.append(r)
    return sorted(out, key=lambda r: r.requested_at)


async def match_entry(session: Session, entry: TimeEntry, client: Client, requests: list[Request]) -> TimeEntry:
    candidates = candidate_requests(entry, requests)
    entry.matched_at = utcnow()
    if not candidates:
        entry.match_reason = "No client request within the matching window."
        session.add(entry)
        session.commit()
        emit(session, "time_unmatched", f"{entry.minutes} min '{entry.description}' ({client.name}) has no matching request.",
             level="warn", client=client.slug, time_entry_id=entry.id)
        return entry
    listing = "\n".join(
        f"{i + 1}. [{fmt_london(r.requested_at)}] {r.summary} (kind {r.kind}; quote: \"{r.quote}\")"
        for i, r in enumerate(candidates)
    )
    prompt_text = (
        f"Client: {client.name}\nTime entry: {fmt_london(entry.started_at)}, {entry.minutes} min, "
        f"project '{entry.project}', description '{entry.description}'\n\n"
        f"Candidate requests ({len(candidates)}):\n{listing}"
    )
    choice = await structured(MATCH_PROMPT, prompt_text, MatchChoice)
    entry.match_confidence = choice.confidence
    entry.match_reason = choice.reason
    n = choice.candidate_number
    if n is None or not 1 <= n <= len(candidates) or choice.confidence < MIN_CONFIDENCE:
        entry.request_id = None
        session.add(entry)
        session.commit()
        emit(session, "time_unmatched",
             f"Left {entry.minutes} min '{entry.description}' unmatched (confidence {choice.confidence:.2f}).",
             level="warn", client=client.slug, time_entry_id=entry.id, reason=choice.reason)
        return entry
    entry.request_id = candidates[n - 1].id
    session.add(entry)
    session.commit()
    return entry


def unmatched_entries(session: Session, client: Client, periods: list[str]) -> list[TimeEntry]:
    from app.models import SourceItem

    rows = session.exec(
        select(TimeEntry, SourceItem).where(
            TimeEntry.client_id == client.id, TimeEntry.matched_at == None,  # noqa: E711
            TimeEntry.source_item_id == SourceItem.id,
        )
    ).all()
    return sorted([te for te, si in rows if si.period in periods], key=lambda t: t.started_at)
