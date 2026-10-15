"""Step 3: extract client requests from a source item (PLAN.md 8.1)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field
from sqlmodel import Session

from app.agent.llm import structured
from app.clock import fmt_london
from app.memory.formatting import channel_of
from app.models import Client, Request, SourceItem

QUOTE_MAX = 200


class ExtractedRequest(BaseModel):
    summary: str = Field(description="One line, plain English, what the client asked for")
    quote: str = Field(description="Short verbatim snippet from the message, max 200 characters")
    kind: Literal["design_change", "new_deliverable", "revision", "bug_fix", "typo_fix", "other"]
    page_or_asset: str | None = Field(None, description="The page or asset concerned, e.g. 'Home', 'Careers page', 'A4 flyer'")
    is_future_work: bool = Field(description="True if the client asks for this to be done later (e.g. next month), not now")


class Extraction(BaseModel):
    requests: list[ExtractedRequest]


EXTRACT_PROMPT = """You read one message a client sent to their freelance designer and list the work the client asks for.
Rules:
- Only count requests from the client for the freelancer to do work.
- Thanks, praise, FYI and chit-chat are not requests: return an empty list.
- kind: "revision" for feedback rounds on an existing page or deliverable; "bug_fix" when something is broken;
  "typo_fix" for correcting a spelling mistake; "new_deliverable" for a new page, document or asset;
  "design_change" for other changes to existing work; "other" otherwise.
- quote must be copied word for word from the message.
- Do not decide whether the work is billable."""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def verified_quote(quote: str, text: str) -> str:
    """Keep the LLM's quote only if it really appears in the message; otherwise quote the message itself."""
    q = _norm(quote)
    if q and q in _norm(text):
        return q[:QUOTE_MAX]
    return _norm(text)[:QUOTE_MAX]


async def extract_requests(session: Session, item: SourceItem, client: Client) -> list[Request]:
    message = (
        f"Client: {client.name}\nDate: {fmt_london(item.occurred_at)} Europe/London\n"
        f"From: {item.author}\nChannel: {channel_of(item)}\n\nMessage:\n{item.text}"
    )
    extraction = await structured(EXTRACT_PROMPT, message, Extraction)
    requests = [
        Request(
            client_id=client.id,
            source_item_id=item.id,
            requested_at=item.occurred_at,
            summary=r.summary.strip(),
            quote=verified_quote(r.quote, item.text),
            kind=r.kind,
            page_or_asset=r.page_or_asset,
            is_future_work=r.is_future_work,
            period=item.period,
        )
        for r in extraction.requests
    ]
    session.add_all(requests)
    session.commit()
    return requests


def meeting_request(item: SourceItem, client: Client) -> Request:
    """Calendar events are always one request of kind 'meeting' (no LLM)."""
    return Request(
        client_id=client.id,
        source_item_id=item.id,
        requested_at=item.occurred_at,
        summary=f"Meeting: {item.title}",
        quote=(item.title or "")[:QUOTE_MAX],
        kind="meeting",
        page_or_asset=None,
        period=item.period,
    )
