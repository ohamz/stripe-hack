from datetime import datetime, timezone

from app.clock import (LONDON, get_now, invoice_due_at, is_period_closed_for_billing, next_period, period_bounds,
                       period_label, period_of, previous_period, set_demo_now)


def test_period_uses_london_time():
    # 23:30 UTC on 31 Oct is still 31 Oct in London (GMT), but 23:30 UTC on 31 Mar is 1 Apr 00:30 BST.
    assert period_of(datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc)) == "2026-10"
    assert period_of(datetime(2026, 3, 31, 23, 30, tzinfo=timezone.utc)) == "2026-04"


def test_period_arithmetic():
    assert next_period("2026-12") == "2027-01"
    assert previous_period("2026-01") == "2025-12"
    assert period_label("2026-10") == "October 2026"
    start, end = period_bounds("2026-10")
    assert start == datetime(2026, 9, 30, 23, tzinfo=timezone.utc)  # 1 Oct 00:00 BST
    assert end == datetime(2026, 11, 1, 0, tzinfo=timezone.utc)  # 1 Nov 00:00 GMT


def test_billing_day_is_the_1st_of_the_next_month():
    assert invoice_due_at("2026-10", 1) == datetime(2026, 11, 1, 0, tzinfo=timezone.utc)
    assert not is_period_closed_for_billing("2026-10", datetime(2026, 10, 31, 18, tzinfo=LONDON), 1)
    assert is_period_closed_for_billing("2026-10", datetime(2026, 11, 1, 9, tzinfo=LONDON), 1)
    assert invoice_due_at("2026-01", 31) == datetime(2026, 2, 28, 0, tzinfo=timezone.utc)  # clamped to month length


def test_demo_clock_overrides_now(session):
    set_demo_now(session, datetime(2026, 10, 31, 18, tzinfo=LONDON))
    assert get_now(session) == datetime(2026, 10, 31, 18, tzinfo=timezone.utc)
    set_demo_now(session, datetime(2026, 11, 1, 9, tzinfo=LONDON))
    assert period_of(get_now(session)) == "2026-11"
    set_demo_now(session, None)
    assert abs((get_now(session) - datetime.now(timezone.utc)).total_seconds()) < 5
