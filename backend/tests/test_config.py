import pytest

from app.config import ConfigError, assert_safe_to_start, llm_key_status, stripe_key_status


@pytest.mark.parametrize("value,state", [("", "missing"), ("sk_test_xxx", "placeholder"), ("sk_live_" + "a" * 40, "live_key_refused"),
                                         ("rk_test_" + "a" * 40, "wrong_format"), ("sk_test_" + "a" * 40, "ok")])
def test_stripe_key_states(monkeypatch, value, state):
    monkeypatch.setenv("STRIPE_SECRET_KEY", value)
    assert stripe_key_status().state == state


def test_live_key_refuses_to_start(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_" + "a" * 40)
    with pytest.raises(ConfigError):
        assert_safe_to_start()


def test_empty_key_disables_billing_but_starts(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    assert_safe_to_start()
    assert not stripe_key_status().ok


@pytest.mark.parametrize("value,ok", [("", False), ("sk-xxx", False), ("sk-proj-" + "a" * 40, True)])
def test_llm_key(monkeypatch, value, ok):
    monkeypatch.setenv("LLM_API_KEY", value)
    assert llm_key_status().ok is ok
