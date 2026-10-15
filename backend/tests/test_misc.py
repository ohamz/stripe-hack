from app.agent.explain import dispute_preconditions
from app.agent.extract import verified_quote
from app.health import badge_for, compute_health, unverified_numbers
from app.models import Decision


def test_quote_must_be_verbatim():
    text = "Hi Maya,\n\nWe've decided we need a Careers page too, same style as Services. Can you add it?"
    assert verified_quote("we need a Careers page too", text) == "we need a Careers page too"
    assert verified_quote("please build a careers page", text).startswith("Hi Maya, We've decided")
    assert len(verified_quote("", "x" * 500)) == 200


def _d(cat, minutes, amount=0, value=0, counts=False):
    return Decision(request_id=0, category=cat, minutes_logged=minutes, amount_pence=amount, value_pence=value,
                    counts_towards_allowance=counts, period="2026-10")


def test_health_numbers_and_badges():
    decisions = [_d("included", 120), _d("billable", 90, 7500, 7500), _d("goodwill", 15, 0, 1250, True),
                 _d("included", 60), _d("goodwill", 10, 0, 1250, False), _d("no_work_logged", 0)]
    h = compute_health(decisions)
    assert (h.minutes_total, h.minutes_in_scope, h.minutes_beyond_scope) == (295, 180, 115)
    assert h.beyond_scope_share_pct == 39.0 and h.badge == "Watch"
    assert (h.favours_used, h.favours_free_kind, h.favours_value_pence, h.amount_billed_pence) == (1, 1, 2500, 7500)
    assert badge_for(19.9) == "Healthy" and badge_for(20) == "Watch" and badge_for(50) == "Watch" and badge_for(50.1) == "Over scope"


def test_narrative_number_check():
    h = compute_health([_d("included", 270), _d("billable", 625, 48750, 48750)])
    assert unverified_numbers(f"About {h.beyond_scope_share_pct}% of the work was extra; £487.50 was billed.", h) == []
    assert unverified_numbers("Around 70% was extra.", h) == []
    assert unverified_numbers("That is 12 extra requests.", h) == ["12"]


def test_dispute_preconditions():
    full = Decision(request_id=1, category="billable", clause_refs=["2.4"], period="2026-10",
                    evidence=[{"type": "source_item"}, {"type": "time_entry"}, {"type": "clause"}])
    assert dispute_preconditions(full) == (True, [])
    meeting = Decision(request_id=1, category="billable", clause_refs=["4.2"], period="2026-10", evidence=[{"type": "source_item"}])
    assert dispute_preconditions(meeting) == (False, ["no matched time entry"])
