"""Source connectors. Each returns RawItem objects; routing to a client happens in app.routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RawItem:
    source: str  # slack | email | calendar | timelog | contract | rules | simulated
    external_id: str
    occurred_at: datetime  # timezone-aware
    author: str
    title: str | None
    text: str
    raw: dict[str, Any]
    # Routing hints: slack_channel, user_name, from_email, to_emails, attendee_emails,
    # calendar_title, timetracker_client, client_slug (contracts, rules, simulated).
    hints: dict[str, Any] = field(default_factory=dict)
