"""Phase checks from PLAN.md section 12 that need the LLM key (run after `make seed`).

Usage:
  python scripts/phase_checks.py phase1   # counts + memory: node sets remembered, recall about 22 October
  python scripts/phase_checks.py phase2   # contract terms + goodwill rules parsed as in section 11
  python scripts/phase_checks.py phase6   # proof link in Stripe + Careers dispute upheld + phone-call dispute escalated

Expected values are copied from PLAN.md section 11 and used only here.
"""

import asyncio
import sys
from collections import Counter

import _path  # noqa: F401

from sqlmodel import select

from app.config import get_settings, llm_key_status
from app.db import init_db, session_scope
from app.memory import cognee_client
from app.models import Client, ContractTerm, GoodwillRule, Invoice, InvoiceLine, Decision, Request, SourceItem

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    results.append((ok, label))
    print(f"{'PASS' if ok else 'FAIL'}  {label}")


def client(session, slug):
    return session.exec(select(Client).where(Client.slug == slug)).one()


async def phase1(session) -> None:
    for slug, expected in {
        "acme": {("contract", None): 1, ("email", "2026-09"): 2, ("timelog", "2026-09"): 1, ("slack", "2026-10"): 8,
                 ("email", "2026-10"): 4, ("calendar", "2026-10"): 3, ("timelog", "2026-10"): 9},
        "bright-bakery": {("contract", None): 1, ("email", "2026-10"): 3, ("calendar", "2026-10"): 1, ("timelog", "2026-10"): 3},
    }.items():
        c = client(session, slug)
        items = session.exec(select(SourceItem).where(SourceItem.client_id == c.id)).all()
        got = Counter((i.source, None if i.source == "contract" else i.period) for i in items)
        for key, n in expected.items():
            check(got[key] == n, f"{slug}: {n} {key[0]} item(s){' in ' + key[1] if key[1] else ''} (got {got[key]})")
        not_remembered = [i for i in items if i.remembered_at is None]
        check(not not_remembered, f"{slug}: every source item remembered in {c.cognee_dataset} ({len(not_remembered)} not)")
        rules = sorted(i.external_id for i in items if i.source == "rules" and i.remembered_at)
        check(any(r.startswith("G1:") for r in rules), f"{slug}: goodwill rule G1 remembered into {c.cognee_dataset} ({rules})")
    unassigned = session.exec(select(SourceItem).where(SourceItem.client_id == None)).all()  # noqa: E711
    check(len(unassigned) == 1, f"1 unassigned time entry (got {len(unassigned)})")
    outcome = await cognee_client.recall("What did Anna ask for on 22 October?", datasets=["client_acme"],
                                         query_type="GRAPH_COMPLETION")
    print("    recall answer:", outcome.answer[:400].replace("\n", " "))
    check("careers" in outcome.answer.lower(), "recall 'What did Anna ask for on 22 October?' mentions the Careers page")


EXPECTED_TERMS = {
    "acme": {"revision_rounds_per_page": 2, "bug_fix_window_days": 30, "delivery_date": "2026-09-30",
             "meetings_per_month": 2, "meeting_max_minutes": 60, "hourly_rate_pence": 5000,
             "billing_increment_minutes": 15, "invoice_day_of_month": 1, "payment_terms_days": 14},
    "bright-bakery": {"revision_rounds_per_page": 2, "bug_fix_window_days": 30, "delivery_date": "2026-09-15",
                      "meetings_per_month": 1, "meeting_max_minutes": 30, "hourly_rate_pence": 5000,
                      "billing_increment_minutes": 15, "invoice_day_of_month": 1, "payment_terms_days": 14},
}
EXPECTED_PAGES = {"acme": {"home", "about", "services", "portfolio", "contact"}, "bright-bakery": 2}
EXPECTED_REFS = {"acme": {"included_pages": "2.1", "revision_rounds_per_page": "3.2", "bug_fix_window_days": "2.3",
                          "meetings_per_month": "4.1", "hourly_rate_pence": "5.2", "billing_increment_minutes": "5.3",
                          "invoice_day_of_month": "5.4"}}


async def phase2(session) -> None:
    for slug, expected in EXPECTED_TERMS.items():
        c = client(session, slug)
        terms = {t.key: t for t in session.exec(select(ContractTerm).where(ContractTerm.client_id == c.id)).all()}
        for key in ["included_pages", "out_of_scope_examples", *expected]:
            check(key in terms, f"{slug}: term {key} present")
        for key, value in expected.items():
            got = terms[key].value_json if key in terms else None
            check(got == value, f"{slug}: {key} = {value!r} (got {got!r})")
        pages = terms["included_pages"].value_json if "included_pages" in terms else []
        exp_pages = EXPECTED_PAGES[slug]
        if isinstance(exp_pages, set):
            check({p.lower().strip() for p in pages} == exp_pages, f"{slug}: included pages {sorted(exp_pages)} (got {pages})")
        else:
            check(len(pages) == exp_pages, f"{slug}: {exp_pages} included deliverables (got {pages})")
        for key, ref in EXPECTED_REFS.get(slug, {}).items():
            got = terms[key].clause_ref if key in terms else None
            check(got == ref, f"{slug}: {key} cites clause {ref} (got {got})")
    rules = {r.rule_ref: r for r in session.exec(select(GoodwillRule)).all()}
    g1, g2 = rules.get("G1"), rules.get("G2")
    check(g1 is not None and g1.client_id is None and g1.params_json == {"type": "small_favour", "max_minutes_exclusive": 20,
                                                                         "max_per_month": 2},
          f"G1 parsed as small_favour <20 min, 2/month, all clients (got {g1.params_json if g1 else None})")
    acme = client(session, "acme")
    check(g2 is not None and g2.client_id == acme.id and g2.params_json == {"type": "always_free_kind", "kind": "typo_fix",
                                                                            "counts_towards_allowance": False},
          f"G2 parsed as always-free typo fixes, not counted, Acme only (got {g2.params_json if g2 else None})")


async def phase6(session) -> None:
    import stripe

    from app.agent.explain import handle_dispute
    from app.billing.stripe_client import configure

    acme = client(session, "acme")
    inv = session.exec(select(Invoice).where(Invoice.client_id == acme.id, Invoice.period == "2026-10")).first()
    if inv is None or not inv.stripe_invoice_id:
        check(False, "Acme October invoice exists (run the billing check first)")
        return
    configure()
    s_inv = stripe.Invoice.retrieve(inv.stripe_invoice_id)
    proof_url = f"{get_settings().public_base_url}/proof/{inv.proof_token}"
    fields = [f.get("value") for f in (s_inv.get("custom_fields") or [])]
    check(proof_url in (s_inv.description or "") or proof_url in fields,
          f"Stripe invoice carries the proof link {proof_url} (description/custom field)")
    careers_item = session.exec(select(SourceItem).where(SourceItem.external_id == "a10.careers@acme-outdoor.example")).one()
    careers_req = session.exec(select(Request).where(Request.source_item_id == careers_item.id)).one()
    careers_dec = session.exec(select(Decision).where(Decision.request_id == careers_req.id)).one()
    line = session.exec(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id,
                                                  InvoiceLine.decision_id == careers_dec.id)).one()
    d1 = await handle_dispute(session, line, "Why are we being charged £200 for the Careers page?", acme)
    print("    reply:", d1.agent_reply)
    check(d1.outcome == "upheld", f"Careers dispute upheld (got {d1.outcome}; {d1.outcome_reason})")
    check("2.1" in d1.agent_reply, "reply cites clause 2.1")
    check("22" in d1.agent_reply and "oct" in d1.agent_reply.lower(), "reply cites Anna's 22 Oct email")
    d2 = await handle_dispute(session, line, "Maya told me on the phone it was free", acme)
    print("    reply:", d2.agent_reply, "|", d2.outcome_reason)
    check(d2.outcome == "escalated", f"'Maya told me on the phone it was free' is escalated (got {d2.outcome})")
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:  # the dispute is remembered in a background task after replying
        await asyncio.gather(*pending, return_exceptions=True)


async def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which not in ("phase1", "phase2", "phase6"):
        print(__doc__)
        return 2
    if not llm_key_status().ok:
        print(f"SKIPPED: {llm_key_status().message}")
        return 2
    init_db()
    with session_scope() as session:
        await {"phase1": phase1, "phase2": phase2, "phase6": phase6}[which](session)
    await cognee_client.wait_for_background_tasks()
    failed = [label for ok, label in results if not ok]
    print(f"\n{which}: {len(results) - len(failed)}/{len(results)} checks passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
