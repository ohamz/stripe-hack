"""Duplicate-invoice guard and invoice line planning (no Stripe calls are made here)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.billing import invoicer
from app.billing.invoicer import billable_description, claim_invoice_slot, goodwill_description, plan_invoice
from app.models import Client, ContractTerm, Decision, Invoice, Request, SourceItem


def _client(session):
    c = Client(slug="acme", name="Acme Outdoor Ltd", contact_name="Anna", contact_email="anna@acme-outdoor.example",
               timetracker_client="Acme Outdoor", cognee_dataset="client_acme")
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def test_claim_slot_only_once(session):
    c = _client(session)
    first = claim_invoice_slot(session, c, "2026-10")
    assert first is not None and len(first.proof_token) >= 24
    assert claim_invoice_slot(session, c, "2026-10") is None
    assert claim_invoice_slot(session, c, "2026-11") is not None


def test_database_unique_constraint(session):
    c = _client(session)
    session.add(Invoice(client_id=c.id, period="2026-10", proof_token="a" * 32))
    session.commit()
    session.add(Invoice(client_id=c.id, period="2026-10", proof_token="b" * 32))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def _seed_decisions(session, c):
    item = SourceItem(client_id=c.id, source="email", external_id="m1", occurred_at=datetime(2026, 10, 22, 8, 5, tzinfo=timezone.utc),
                      author="Anna", text="Careers page please", period="2026-10")
    session.add(item)
    session.commit()
    rows = [("Careers page design", "billable", 240, 20000, 20000, ["2.4"], 22),
            ("Footer logo swap", "goodwill", 15, 0, 1250, ["2.4"], 8),
            ("Home page round 2", "included", 0, 0, 0, ["3.2"], 3),
            ("Unclear request", "needs_review", 0, 0, 0, [], 12)]
    for summary, cat, billed, amount, value, refs, day in rows:
        r = Request(client_id=c.id, source_item_id=item.id, requested_at=datetime(2026, 10, day, 9, tzinfo=timezone.utc),
                    summary=summary, kind="other", period="2026-10")
        session.add(r)
        session.commit()
        session.add(Decision(request_id=r.id, category=cat, minutes_billed=billed, amount_pence=amount, value_pence=value,
                             clause_refs=refs, period="2026-10"))
    session.commit()


def test_plan_lines_and_descriptions(session):
    c = _client(session)
    _seed_decisions(session, c)
    plan = plan_invoice(session, c, "2026-10", 5000)
    assert [p.description for p in plan.billable] == ["Careers page design (22 Oct, 240 min @ £50/h, clause 2.4)"]
    assert [p.description for p in plan.goodwill] == ["On the house: Footer logo swap (8 Oct, worth £12.50)"]
    assert plan.total_pence == 20000 and plan.goodwill_value_pence == 1250 and plan.needs_review == 1
    assert all(p.amount_pence == 0 for p in plan.goodwill)
    assert billable_description("x", "1 Oct", 15, 5000, ["2.4", "5.2"]) == "x (1 Oct, 15 min @ £50/h, clause 2.4, 5.2)"
    assert goodwill_description("y", "2 Oct", 1250) == "On the house: y (2 Oct, worth £12.50)"


def test_failed_run_is_not_retried(session, monkeypatch):
    """A Stripe failure leaves a 'failed' row; the next run sees it and never raises a second invoice."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")  # configure() raises StripeDisabled inside the run
    c = _client(session)
    _seed_decisions(session, c)
    for key, value, ref in [("hourly_rate_pence", 5000, "5.2"), ("payment_terms_days", 14, "5.4")]:
        session.add(ContractTerm(client_id=c.id, clause_ref=ref, key=key, value_json=value))
    session.commit()
    monkeypatch.setattr(invoicer, "load_terms", lambda s, client: type("T", (), {"hourly_rate_pence": 5000, "payment_terms_days": 14})())
    first = invoicer.raise_invoice_sync(c.id, "2026-10")
    assert first["status"] == "failed" and "StripeDisabled" in first["error"]
    second = invoicer.raise_invoice_sync(c.id, "2026-10")
    assert second == {"status": "already_invoiced"}
    rows = session.exec(select(Invoice)).all()
    assert len(rows) == 1 and rows[0].status == "failed"
