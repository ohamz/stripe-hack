from datetime import datetime, timedelta, timezone

from app.agent.decide import (BILLABLE, GOODWILL, INCLUDED, NEEDS_REVIEW, RuleView, ScopeCheck, favours_used_before,
                              goodwill_outcome, verdict_from_scope)
from app.agent.terms import Terms
from app.models import Decision, Request

G1 = RuleView("G1", {"type": "small_favour", "max_minutes_exclusive": 20, "max_per_month": 2})
G2 = RuleView("G2", {"type": "always_free_kind", "kind": "typo_fix", "counts_towards_allowance": False})


def test_small_favours_until_allowance_runs_out():
    assert goodwill_outcome(15, "design_change", False, [G1], 0).is_goodwill
    assert goodwill_outcome(15, "design_change", False, [G1], 1).is_goodwill
    third = goodwill_outcome(15, "design_change", False, [G1], 2)
    assert not third.is_goodwill and third.exhausted_rule_ref == "G1"


def test_under_means_strictly_under():
    assert goodwill_outcome(19, "other", False, [G1], 0).is_goodwill
    out = goodwill_outcome(20, "other", False, [G1], 0)
    assert not out.is_goodwill and out.exhausted_rule_ref is None


def test_typo_rule_is_free_and_does_not_use_allowance():
    out = goodwill_outcome(10, "typo_fix", True, [G2, G1], 2)
    assert out.is_goodwill and out.rule_ref == "G2" and out.counts_towards_allowance is False


def test_typo_rule_only_for_typos():
    out = goodwill_outcome(10, "design_change", False, [G2, G1], 2)
    assert not out.is_goodwill and out.exhausted_rule_ref == "G1"


def test_no_rules_means_billable():
    assert goodwill_outcome(5, "other", False, [], 0) .is_goodwill is False


def _req(i, day, client=1, period="2026-10"):
    return Request(id=i, client_id=client, source_item_id=i, kind="other", summary=f"r{i}", period=period,
                   requested_at=datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(days=day))


def test_favours_counted_by_request_date_and_only_when_counting():
    r1, r2, r3, r4 = _req(1, 7), _req(2, 15), _req(3, 28), _req(4, 20)
    decided = [
        (r1, Decision(request_id=1, category=GOODWILL, counts_towards_allowance=True, period="2026-10")),
        (r2, Decision(request_id=2, category=GOODWILL, counts_towards_allowance=True, period="2026-10")),
        (r3, Decision(request_id=3, category=GOODWILL, counts_towards_allowance=False, period="2026-10")),  # typo rule
    ]
    assert favours_used_before(decided, r4) == 2
    assert favours_used_before(decided, _req(5, 10)) == 1
    other_client = _req(6, 25, client=2)
    assert favours_used_before(decided, other_client) == 0
    other_month = _req(7, 40, period="2026-11")
    assert favours_used_before(decided, other_month) == 0


TERMS = Terms(values={"revision_rounds_per_page": 2, "delivery_date": "2026-09-30", "bug_fix_window_days": 30},
              refs={}, clauses={"2.1": "...", "2.3": "...", "2.4": "...", "3.2": "...", "3.3": "..."})


def _check(**kw):
    base = dict(in_scope=False, clause_refs=["2.4"], revision_round=None, is_typo_fix=False, reasoning="r", confidence=0.9)
    return ScopeCheck(**{**base, **kw})


def test_low_confidence_needs_review():
    v = verdict_from_scope(_check(confidence=0.6), _req(1, 1), 15, TERMS, [G1], 0)
    assert v.category == NEEDS_REVIEW


def test_in_scope_is_included():
    v = verdict_from_scope(_check(in_scope=True, clause_refs=["2.3"]), _req(1, 1), 30, TERMS, [G1], 0)
    assert v.category == INCLUDED and v.clause_refs == ["2.3"]


def test_out_of_scope_small_is_goodwill_then_billable():
    assert verdict_from_scope(_check(), _req(1, 1), 15, TERMS, [G1], 1).category == GOODWILL
    v = verdict_from_scope(_check(), _req(1, 1), 15, TERMS, [G1], 2)
    assert v.category == BILLABLE and v.rule_refs == ["G1"]


def test_big_out_of_scope_job_is_billable_without_rule_ref():
    v = verdict_from_scope(_check(), _req(1, 1), 240, TERMS, [G1], 0)
    assert v.category == BILLABLE and v.rule_refs == []


def test_inconsistent_revision_count_needs_review():
    v = verdict_from_scope(_check(in_scope=True, clause_refs=["3.2"], revision_round=3), _req(1, 1), 90, TERMS, [G1], 0)
    assert v.category == NEEDS_REVIEW


def test_unknown_clause_refs_are_dropped_and_none_left_needs_review():
    v = verdict_from_scope(_check(clause_refs=["9.9"]), _req(1, 1), 90, TERMS, [G1], 0)
    assert v.category == NEEDS_REVIEW
    v = verdict_from_scope(_check(clause_refs=["9.9", "2.4"]), _req(1, 1), 90, TERMS, [G1], 0)
    assert v.category == BILLABLE and v.clause_refs == ["2.4"]
