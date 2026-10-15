"""Step 1: ingest. Normalise connector output into SourceItem rows (and TimeEntry rows), routed to clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from app.clock import period_of
from app.config import DEMO_DATA_DIR
from app.connectors import RawItem
from app.connectors.calendar_ics import load_calendar_dir
from app.connectors.contract import load_contract, load_goodwill_rules
from app.connectors.email_files import load_email_dir
from app.connectors.slack_file import load_slack_dir
from app.connectors.timelog_csv import load_timelog_dir
from app.memory.cognee_client import dataset_for
from app.models import Client, GoodwillRule, SourceItem, TimeEntry
from app.routing import Registry, load_registry, route


@dataclass
class IngestReport:
    created: dict[str, int] = field(default_factory=dict)
    existing: int = 0
    unassigned: int = 0
    new_item_ids: list[int] = field(default_factory=list)

    def add(self, source: str) -> None:
        self.created[source] = self.created.get(source, 0) + 1


def sync_clients(session: Session, registry: Registry) -> dict[str, Client]:
    by_slug: dict[str, Client] = {}
    for spec in registry.clients:
        client = session.exec(select(Client).where(Client.slug == spec.slug)).first()
        if client is None:
            client = Client(slug=spec.slug, cognee_dataset=dataset_for(spec.slug), name=spec.name,
                            contact_name=spec.contact_name, contact_email=spec.contact_email,
                            timetracker_client=spec.timetracker_client)
        client.name = spec.name
        client.contact_name = spec.contact_name
        client.contact_email = spec.contact_email
        client.email_domains = list(spec.email_domains)
        client.slack_channels = list(spec.slack_channels)
        client.slack_user_names = list(spec.slack_user_names)
        client.calendar_match = list(spec.calendar_match)
        client.timetracker_client = spec.timetracker_client
        client.contract_file = spec.contract_file
        session.add(client)
        session.commit()
        session.refresh(client)
        by_slug[spec.slug] = client
    return by_slug


def store_item(session: Session, raw: RawItem, client: Client | None, report: IngestReport) -> SourceItem | None:
    existing = session.exec(
        select(SourceItem).where(SourceItem.source == raw.source, SourceItem.external_id == raw.external_id)
    ).first()
    if existing is not None:
        report.existing += 1
        return None
    item = SourceItem(
        client_id=client.id if client else None,
        source=raw.source,
        external_id=raw.external_id,
        occurred_at=raw.occurred_at.astimezone(timezone.utc),
        author=raw.author,
        title=raw.title,
        text=raw.text,
        raw_json=raw.raw,
        period=period_of(raw.occurred_at),
        cognee_dataset=client.cognee_dataset if client else None,
        cognee_node_set=[_node_set_name(raw.source), client.slug] if client else [],
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    report.add(raw.source)
    report.new_item_ids.append(item.id)
    if client is None:
        report.unassigned += 1
    if raw.source == "timelog":
        session.add(
            TimeEntry(
                source_item_id=item.id,
                client_id=client.id if client else None,
                started_at=item.occurred_at,
                minutes=int(raw.raw["duration_minutes"]),
                project=raw.raw.get("project", ""),
                description=raw.raw.get("description", ""),
            )
        )
        session.commit()
    return item


def _node_set_name(source: str) -> str:
    return {"rules": "goodwill_rules"}.get(source, source)


def ingest_raw_items(session: Session, raw_items: list[RawItem], registry: Registry, clients: dict[str, Client]) -> IngestReport:
    report = IngestReport()
    for raw in raw_items:
        spec = route(raw, registry)
        store_item(session, raw, clients[spec.slug] if spec else None, report)
    return report


def sync_goodwill_rules(session: Session, rules: list[dict], clients: dict[str, Client], report: IngestReport, now: datetime) -> None:
    """GoodwillRule rows, plus one 'rules' SourceItem per client each rule applies to (for memory)."""
    for rule in rules:
        targets = list(clients.values()) if rule["applies_to"] == "all" else [clients[s] for s in rule["applies_to"] if s in clients]
        missing = [] if rule["applies_to"] == "all" else [s for s in rule["applies_to"] if s not in clients]
        if missing:
            raise ValueError(f"goodwill rule {rule['rule_ref']} names unknown clients {missing}")
        row_client_ids = [None] if rule["applies_to"] == "all" else [c.id for c in targets]
        for client_id in row_client_ids:
            row = session.exec(
                select(GoodwillRule).where(GoodwillRule.rule_ref == rule["rule_ref"], GoodwillRule.client_id == client_id)
            ).first()
            if row is None:
                row = GoodwillRule(client_id=client_id, rule_ref=rule["rule_ref"], text=rule["text"])
            elif row.text != rule["text"]:
                row.text, row.params_json, row.parse_status, row.parse_note = rule["text"], None, "pending", None
            session.add(row)
        session.commit()
        for client in targets:
            raw = RawItem(
                source="rules",
                external_id=f"{rule['rule_ref']}:{client.slug}",
                occurred_at=now,
                author="Maya Chen",
                title=f"Goodwill rule {rule['rule_ref']}",
                text=f"Goodwill rule {rule['rule_ref']} ({'all clients' if rule['applies_to'] == 'all' else client.name}): {rule['text']}",
                raw=rule,
                hints={"client_slug": client.slug},
            )
            store_item(session, raw, client, report)


def load_demo_sources(session: Session, demo_dir: Path = DEMO_DATA_DIR, now: datetime | None = None) -> IngestReport:
    """Load every demo file (section 11) into SourceItems. Idempotent."""
    registry = load_registry(demo_dir / "clients.yaml")
    clients = sync_clients(session, registry)
    raw: list[RawItem] = []
    for spec in registry.clients:
        raw.append(load_contract(demo_dir / spec.contract_file, spec.slug))
    raw += load_slack_dir(demo_dir / "slack")
    raw += load_email_dir(demo_dir / "email")
    raw += load_calendar_dir(demo_dir / "calendar")
    raw += load_timelog_dir(demo_dir / "timelog", author=registry.freelancer.get("name", "Freelancer"))
    report = ingest_raw_items(session, raw, registry, clients)
    sync_goodwill_rules(session, load_goodwill_rules(demo_dir / "goodwill_rules.md"), clients, report,
                        now or datetime.now(timezone.utc))
    return report


def registry() -> Registry:
    return load_registry(DEMO_DATA_DIR / "clients.yaml")
