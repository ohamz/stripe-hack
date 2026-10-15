"""Phase 4 check: jump the demo clock to 2026-11-01 09:00 and let the billing job raise the invoices.

Expected (PLAN.md 12, Phase 4): exactly one Acme invoice of £487.50 in Stripe test mode with 5 billable lines and
3 goodwill lines, no Bright Bakery invoice, and a second run creates nothing new.

  python scripts/billing_check.py          # raise + verify
  python scripts/billing_check.py --pay    # also pay it with Stripe's test payment method and confirm Tab marks it paid

Payment: Invoice.pay(payment_method=...) requires a PaymentMethod that belongs to the customer (Stripe docs,
"Pay an invoice"), so the test card pm_card_visa is attached to the customer first.
"""

import argparse
import asyncio
import sys
from datetime import datetime

import _path  # noqa: F401

import stripe
from sqlmodel import select

from app.billing.invoicer import run_billing_job
from app.billing.stripe_client import StripeDisabled, configure
from app.billing.webhooks import poll_open_invoices
from app.clock import LONDON, set_demo_now
from app.config import stripe_key_status
from app.db import init_db, session_scope
from app.models import Client, Invoice, InvoiceLine

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    results.append((ok, label))
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pay", action="store_true")
    args = parser.parse_args()
    if not stripe_key_status().ok:
        print(f"SKIPPED: {stripe_key_status().message}")
        return 2
    try:
        configure()
    except StripeDisabled as exc:
        print(f"SKIPPED: {exc}")
        return 2
    init_db()
    with session_scope() as session:
        set_demo_now(session, datetime(2026, 11, 1, 9, 0, tzinfo=LONDON))
        first = await run_billing_job(session)
        print("billing run 1:", first)
        acme = session.exec(select(Client).where(Client.slug == "acme")).one()
        bakery = session.exec(select(Client).where(Client.slug == "bright-bakery")).one()
        acme_invs = session.exec(select(Invoice).where(Invoice.client_id == acme.id)).all()
        bakery_invs = session.exec(select(Invoice).where(Invoice.client_id == bakery.id)).all()
        check(len(acme_invs) == 1, f"exactly one Acme invoice (got {len(acme_invs)})")
        check(not bakery_invs, f"no Bright Bakery invoice (got {len(bakery_invs)})")
        if len(acme_invs) != 1:
            return 1
        inv = acme_invs[0]
        check(inv.status == "open", f"Acme invoice status open (got {inv.status}; error {inv.error})")
        check(inv.total_pence == 48750, f"Tab total £487.50 (got £{inv.total_pence / 100:.2f})")
        lines = session.exec(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)).all()
        check(sum(not line.is_goodwill for line in lines) == 5, f"5 billable lines (got {sum(not line.is_goodwill for line in lines)})")
        check(sum(line.is_goodwill for line in lines) == 3, f"3 goodwill lines (got {sum(line.is_goodwill for line in lines)})")
        print("notes:", inv.notes)

        s_inv = stripe.Invoice.retrieve(inv.stripe_invoice_id)
        s_lines = stripe.Invoice.list_lines(inv.stripe_invoice_id, limit=100)
        check(s_inv.livemode is False, "Stripe invoice is in test mode")
        check(s_inv.total == 48750 and s_inv.currency == "gbp", f"Stripe total £487.50 GBP (got {s_inv.total} {s_inv.currency})")
        zero = [li for li in s_lines.data if li.amount == 0]
        print(f"Stripe lines: {len(s_lines.data)} ({len(zero)} at £0); footer: {s_inv.footer!r}")
        check(len(s_lines.data) == 8 or (len(s_lines.data) == 5 and s_inv.footer),
              "Stripe has 8 lines (or 5 + goodwill footer fallback)")
        check(bool(s_inv.hosted_invoice_url), f"hosted invoice URL: {s_inv.hosted_invoice_url}")

        second = await run_billing_job(session)
        print("billing run 2:", second)
        after = session.exec(select(Invoice)).all()
        check(len(after) == 1 and not [r for r in second if r.get("status") == "raised"], "second run creates nothing new")
        listed = stripe.Invoice.list(customer=inv.stripe_customer_id, limit=10)
        same_period = [i for i in listed.data if (i.metadata or {}).get("period") == "2026-10"]
        check(len(same_period) == 1, f"Stripe has exactly one 2026-10 invoice for the customer (got {len(same_period)})")

        if args.pay:
            pm = stripe.PaymentMethod.attach("pm_card_visa", customer=inv.stripe_customer_id)
            paid = stripe.Invoice.pay(inv.stripe_invoice_id, payment_method=pm.id)
            print(f"Stripe pay(): status {paid.status}")
            await poll_open_invoices(session)
            session.refresh(inv)
            check(inv.status == "paid", f"Tab marks the invoice paid (got {inv.status})")
    failed = [label for ok, label in results if not ok]
    print(f"\nphase4: {len(results) - len(failed)}/{len(results)} checks passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
