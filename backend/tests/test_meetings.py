from datetime import datetime, timedelta, timezone

from app.agent.decide import BILLABLE, INCLUDED, meeting_number, meeting_verdict
from app.models import Request


def test_meetings_within_count_and_length_are_included():
    v = meeting_verdict(2, 60, 2, 60, "4.1", "4.2")
    assert (v.category, v.minutes_logged, v.billable_minutes, v.clause_refs) == (INCLUDED, 60, 0, ["4.1"])


def test_third_meeting_is_billed_whole():
    v = meeting_verdict(3, 60, 2, 60, "4.1", "4.2")
    assert (v.category, v.minutes_logged, v.billable_minutes, v.clause_refs) == (BILLABLE, 60, 60, ["4.2"])


def test_overlong_meeting_bills_only_the_extra_minutes():
    v = meeting_verdict(1, 90, 2, 60, "4.1", "4.2")
    assert (v.category, v.minutes_logged, v.billable_minutes) == (BILLABLE, 90, 30)


def test_one_meeting_allowance():
    assert meeting_verdict(1, 30, 1, 30, "4.1", "4.2").category == INCLUDED
    assert meeting_verdict(2, 30, 1, 30, "4.1", "4.2").category == BILLABLE


def test_meeting_number_is_by_date_not_insertion_order():
    base = datetime(2026, 10, 13, 9, tzinfo=timezone.utc)
    m = [Request(id=i, client_id=1, source_item_id=i, requested_at=base + timedelta(days=d), summary="", kind="meeting",
                 period="2026-10") for i, d in [(10, 14), (11, 0), (12, 7)]]
    assert [meeting_number(m, r) for r in m] == [3, 1, 2]
