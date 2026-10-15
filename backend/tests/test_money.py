import pytest

from app.agent.decide import BILLABLE, GOODWILL, INCLUDED, NEEDS_REVIEW, NO_WORK, Verdict, money_for
from app.money import billed_minutes, format_gbp, format_rate, value_pence


@pytest.mark.parametrize("logged,expected", [(0, 0), (1, 15), (10, 15), (15, 15), (16, 30), (90, 90), (240, 240), (61, 75)])
def test_rounding_up_to_15(logged, expected):
    assert billed_minutes(logged, 15) == expected


def test_rounding_rejects_bad_input():
    with pytest.raises(ValueError):
        billed_minutes(10, 0)
    with pytest.raises(ValueError):
        billed_minutes(-5, 15)


@pytest.mark.parametrize("minutes,pence", [(15, 1250), (60, 5000), (90, 7500), (180, 15000), (240, 20000)])
def test_value_at_50_per_hour(minutes, pence):
    assert value_pence(minutes, 5000) == pence


def test_value_never_rounds_money_silently():
    with pytest.raises(ValueError):
        value_pence(7, 5000)  # 7 * 5000 / 60 is not whole pence


def test_formatting():
    assert format_gbp(48750) == "£487.50"
    assert format_gbp(1250) == "£12.50"
    assert format_gbp(400000) == "£4,000.00"
    assert format_rate(5000) == "£50/h"
    assert format_rate(5250) == "£52.50/h"


def test_money_by_category():
    assert money_for(Verdict(BILLABLE, 10, 10), 15, 5000).__dict__ == {"minutes_billed": 15, "amount_pence": 1250, "value_pence": 1250}
    assert money_for(Verdict(GOODWILL, 10, 10), 15, 5000).__dict__ == {"minutes_billed": 15, "amount_pence": 0, "value_pence": 1250}
    for cat in (INCLUDED, NEEDS_REVIEW, NO_WORK):
        assert money_for(Verdict(cat, 120, 0), 15, 5000).__dict__ == {"minutes_billed": 0, "amount_pence": 0, "value_pence": 0}
