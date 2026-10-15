"""Stripe setup. Test mode only: a missing key disables billing, a non-test key refuses to start."""

from __future__ import annotations

import stripe

from app.config import ConfigError, get_settings, stripe_key_status


class StripeDisabled(RuntimeError):
    pass


def configure() -> None:
    status = stripe_key_status()
    if status.state in ("live_key_refused", "wrong_format"):
        raise ConfigError(status.message)
    if not status.ok:
        raise StripeDisabled(status.message)
    stripe.api_key = get_settings().stripe_secret_key
    # Retries are safe because every create call carries an idempotency key.
    stripe.max_network_retries = 2


def account_summary() -> dict:
    configure()
    acct = stripe.Account.retrieve()
    return {"id": acct.id, "livemode": False, "display_name": getattr(acct, "settings", None) and
            acct.settings.get("dashboard", {}).get("display_name")}
