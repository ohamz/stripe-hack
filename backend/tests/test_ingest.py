"""Phase 1 SourceItem counts (PLAN.md section 12, Phase 1 check), without any API key."""

from collections import Counter
from datetime import datetime, timezone

from sqlmodel import select

from app.ingest import load_demo_sources
from app.models import Client, GoodwillRule, SourceItem, TimeEntry


def _counts(session, slug, period=None):
    client = session.exec(select(Client).where(Client.slug == slug)).one()
    q = select(SourceItem).where(SourceItem.client_id == client.id)
    items = session.exec(q).all()
    return Counter((i.source, i.period) for i in items if period is None or i.period == period), items


def test_phase1_counts(session):
    load_demo_sources(session, now=datetime(2026, 10, 31, 18, tzinfo=timezone.utc))
    acme, acme_items = _counts(session, "acme")
    assert sum(1 for i in acme_items if i.source == "contract") == 1
    assert acme[("email", "2026-09")] == 2
    assert acme[("timelog", "2026-09")] == 1
    assert acme[("slack", "2026-10")] == 8
    assert acme[("email", "2026-10")] == 4
    assert acme[("calendar", "2026-10")] == 3
    assert acme[("timelog", "2026-10")] == 9

    bakery, bakery_items = _counts(session, "bright-bakery")
    assert sum(1 for i in bakery_items if i.source == "contract") == 1
    assert bakery[("email", "2026-10")] == 3
    assert bakery[("calendar", "2026-10")] == 1
    assert bakery[("timelog", "2026-10")] == 3

    unassigned = session.exec(select(SourceItem).where(SourceItem.client_id == None)).all()  # noqa: E711
    assert [(u.source, u.raw_json["project"]) for u in unassigned] == [("timelog", "Portfolio site update")]
    assert session.exec(select(TimeEntry).where(TimeEntry.client_id == None)).one().minutes == 60  # noqa: E711

    # Goodwill rules go into each client dataset they apply to: G1 -> both, G2 -> Acme only.
    rules = {(i.external_id, i.cognee_dataset) for i in acme_items + bakery_items if i.source == "rules"}
    assert rules == {("G1:acme", "client_acme"), ("G2:acme", "client_acme"), ("G1:bright-bakery", "client_bright-bakery")}
    g = {(r.rule_ref, r.client_id is None) for r in session.exec(select(GoodwillRule)).all()}
    assert g == {("G1", True), ("G2", False)}

    # Node sets follow PLAN.md 7.1.
    assert {tuple(i.cognee_node_set) for i in acme_items} == {
        ("contract", "acme"), ("email", "acme"), ("slack", "acme"), ("calendar", "acme"),
        ("timelog", "acme"), ("goodwill_rules", "acme")}


def test_ingest_is_idempotent(session):
    first = load_demo_sources(session)
    second = load_demo_sources(session)
    assert sum(first.created.values()) > 0
    assert sum(second.created.values()) == 0
    assert len(session.exec(select(TimeEntry)).all()) == 14


def test_times_are_london(session):
    load_demo_sources(session)
    a03 = session.exec(select(SourceItem).where(SourceItem.external_id == "acme-website:1791291900")).one()
    assert a03.occurred_at == datetime(2026, 10, 6, 13, 5, tzinfo=timezone.utc)  # 14:05 BST
    a12 = session.exec(select(SourceItem).where(SourceItem.external_id == "a12-acme-sync-20261027@mayachen.example")).one()
    assert a12.occurred_at == datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)  # 10:00 GMT after clocks change
    assert a12.raw_json["minutes"] == 60
