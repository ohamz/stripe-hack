from datetime import datetime, timezone

from app.config import DEMO_DATA_DIR
from app.connectors import RawItem
from app.routing import load_registry, route

REG = load_registry(DEMO_DATA_DIR / "clients.yaml")
T = datetime(2026, 10, 1, tzinfo=timezone.utc)


def item(source, **hints):
    return RawItem(source=source, external_id="x", occurred_at=T, author="", title=None, text="", raw={}, hints=hints)


def slug(i):
    c = route(i, REG)
    return c.slug if c else None


def test_slack_by_channel_or_user():
    assert slug(item("slack", slack_channel="acme-website", user_name="")) == "acme"
    assert slug(item("slack", slack_channel="random", user_name="Anna Kowalski")) == "acme"
    assert slug(item("slack", slack_channel="random", user_name="Someone")) is None


def test_email_by_domain():
    assert slug(item("email", from_email="anna@acme-outdoor.example", to_emails=["maya@mayachen.example"])) == "acme"
    assert slug(item("email", from_email="tom@brightbakery.example", to_emails=[])) == "bright-bakery"
    assert slug(item("email", from_email="maya@mayachen.example", to_emails=["tom@brightbakery.example"])) == "bright-bakery"
    assert slug(item("email", from_email="spam@else.example", to_emails=["maya@mayachen.example"])) is None


def test_calendar_by_title_or_attendee():
    assert slug(item("calendar", calendar_title="Acme weekly sync", attendee_emails=[])) == "acme"
    assert slug(item("calendar", calendar_title="Catch-up", attendee_emails=["tom@brightbakery.example"])) == "bright-bakery"
    assert slug(item("calendar", calendar_title="Dentist", attendee_emails=[])) is None


def test_ambiguous_items_are_unassigned():
    i = item("calendar", calendar_title="Acme x Bright Bakery intro", attendee_emails=[])
    assert slug(i) is None


def test_timelog_by_client_column():
    assert slug(item("timelog", timetracker_client="Acme Outdoor")) == "acme"
    assert slug(item("timelog", timetracker_client="bright bakery ")) == "bright-bakery"
    assert slug(item("timelog", timetracker_client="")) is None


def test_explicit_client_for_contracts_and_simulated():
    assert slug(item("contract", client_slug="bright-bakery")) == "bright-bakery"
    assert slug(item("simulated", client_slug="acme")) == "acme"
