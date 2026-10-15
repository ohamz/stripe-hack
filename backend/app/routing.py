"""Deterministic client routing (PLAN.md 6.1). Never guessed by the LLM.

An item that matches no client, or more than one, is unassigned (client_id = null, never billed).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.connectors import RawItem


@dataclass(frozen=True)
class ClientSpec:
    slug: str
    name: str
    contact_name: str
    contact_email: str
    email_domains: tuple[str, ...]
    slack_channels: tuple[str, ...]
    slack_user_names: tuple[str, ...]
    calendar_match: tuple[str, ...]
    timetracker_client: str
    contract_file: str


@dataclass(frozen=True)
class Registry:
    freelancer: dict
    clients: tuple[ClientSpec, ...]


def load_registry(path: Path) -> Registry:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    clients = []
    for c in data.get("clients", []):
        clients.append(
            ClientSpec(
                slug=c["slug"],
                name=c["name"],
                contact_name=c.get("contact_name", ""),
                contact_email=c.get("contact_email", ""),
                email_domains=tuple(d.lower() for d in c.get("email_domains") or []),
                slack_channels=tuple(c.get("slack_channels") or []),
                slack_user_names=tuple(c.get("slack_user_names") or []),
                calendar_match=tuple(c.get("calendar_match") or []),
                timetracker_client=c.get("timetracker_client", ""),
                contract_file=c.get("contract_file", ""),
            )
        )
    slugs = [c.slug for c in clients]
    if len(set(slugs)) != len(slugs):
        raise ValueError("duplicate client slugs in clients.yaml")
    return Registry(freelancer=data.get("freelancer", {}), clients=tuple(clients))


def _domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower() if "@" in email else ""


def _matches(item: RawItem, c: ClientSpec) -> bool:
    h = item.hints
    if h.get("client_slug"):
        return h["client_slug"] == c.slug
    if item.source == "slack":
        return h.get("slack_channel") in c.slack_channels or (
            bool(h.get("user_name")) and h.get("user_name") in c.slack_user_names
        )
    if item.source == "email":
        domains = {_domain(h.get("from_email", ""))} | {_domain(e) for e in h.get("to_emails", [])}
        return bool(domains & set(c.email_domains))
    if item.source == "calendar":
        title = (h.get("calendar_title") or "").lower()
        if any(m.lower() in title for m in c.calendar_match if m):
            return True
        return any(_domain(e) in c.email_domains for e in h.get("attendee_emails", []))
    if item.source == "timelog":
        value = (h.get("timetracker_client") or "").strip().lower()
        return bool(value) and value == c.timetracker_client.strip().lower()
    return False


def route(item: RawItem, registry: Registry) -> ClientSpec | None:
    """Return the single matching client, or None if no client (or several) match."""
    matches = [c for c in registry.clients if _matches(item, c)]
    return matches[0] if len(matches) == 1 else None
