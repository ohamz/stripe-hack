"""Phase 0 smoke test (b): the Stripe test key creates and deletes a test Customer."""

import importlib.metadata as md

import _path  # noqa: F401

import stripe

from app.billing.stripe_client import StripeDisabled, configure


def main() -> int:
    print(f"stripe library {md.version('stripe')}, API version {stripe.api_version}")
    try:
        configure()
    except StripeDisabled as exc:
        print(f"SKIPPED: {exc}")
        return 2
    customer = stripe.Customer.create(name="Tab smoke test", email="smoke@tab.example",
                                      metadata={"tab_smoke_test": "1"})
    print(f"created {customer.id} livemode={customer.livemode}")
    if customer.livemode:
        print("FAIL: customer created in live mode")
        return 1
    deleted = stripe.Customer.delete(customer.id)
    print(f"deleted {deleted.id}: {deleted.deleted}")
    print("PASS" if deleted.deleted else "FAIL")
    return 0 if deleted.deleted else 1


if __name__ == "__main__":
    raise SystemExit(main())
