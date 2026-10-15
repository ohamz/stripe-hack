"""make acceptance: load the demo, run the pipeline, compare with PLAN.md section 13.

The expected values below are copied from PLAN.md section 13 and are used ONLY here.
Do not edit them to make the tests pass.

Usage: python scripts/acceptance.py [--no-run]   (--no-run: compare the current database without running the pipeline)
For a fresh run from nothing: make reset && make acceptance
"""

import argparse
import asyncio
import sys

import _path  # noqa: F401

from sqlmodel import select

from app.config import llm_key_status
from app.db import init_db, session_scope
from app.health import compute_health
from app.memory import cognee_client
from app.seed import seed
from app.models import Client, Decision, Request, SourceItem, TimeEntry

# Section 11 IDs -> the demo source item they come from.
SOURCE_IDS = {
    "A02": ("email", "a02.home-round2@acme-outdoor.example"),
    "A03": ("slack", "acme-website:1791291900"),
    "A04": ("slack", "acme-website:1791454800"),
    "N01": ("slack", "acme-website:1791532500"),
    "A05": ("email", "a05.flyer@acme-outdoor.example"),
    "A06": ("calendar", "a06-acme-sync-20261013@mayachen.example"),
    "N02": ("email", "n02.fyi@acme-outdoor.example"),
    "A07": ("slack", "acme-website:1792152600"),
    "A08": ("calendar", "a08-acme-sync-20261020@mayachen.example"),
    "A09": ("slack", "acme-website:1792593900"),
    "A10": ("email", "a10.careers@acme-outdoor.example"),
    "A11": ("slack", "acme-website:1792858800"),
    "A12": ("calendar", "a12-acme-sync-20261027@mayachen.example"),
    "A13": ("slack", "acme-website:1793275200"),
    "A14": ("slack", "acme-website:1793376000"),
    "B01": ("email", "b01.menu-round1@brightbakery.example"),
    "B02": ("calendar", "b02-bakery-checkin-20261012@mayachen.example"),
    "B03": ("email", "b03.croissant@brightbakery.example"),
    "B04": ("email", "b04.menu-round2@brightbakery.example"),
}

# PLAN.md 13.1 / 13.2. clauses: every listed ref must be cited ("any" = at least one of them).
# rules: every listed goodwill rule must be cited. round: expected revision round.
EXPECTED = {
    "A02": dict(category="included", minutes=120, billed=0, amount=0, value=0, clauses=["3.2"], round=2),
    "A03": dict(category="billable", minutes=90, billed=90, amount=7500, value=7500, clauses=["3.3"], round=3),
    "A04": dict(category="goodwill", minutes=15, billed=15, amount=0, value=1250, rules=["G1"], favour=1),
    "A05": dict(category="billable", minutes=180, billed=180, amount=15000, value=15000, clauses=["2.4"]),
    "A06": dict(category="included", minutes=60, billed=0, amount=0, value=0, clauses=["4.1"]),
    "A07": dict(category="goodwill", minutes=15, billed=15, amount=0, value=1250, rules=["G1"], favour=2),
    "A08": dict(category="included", minutes=60, billed=0, amount=0, value=0, clauses=["4.1"]),
    "A09": dict(category="billable", minutes=15, billed=15, amount=1250, value=1250, clauses=["2.4"], rules=["G1"]),
    "A10": dict(category="billable", minutes=240, billed=240, amount=20000, value=20000, any_clauses=["2.1", "2.4"]),
    "A11": dict(category="included", minutes=30, billed=0, amount=0, value=0, clauses=["2.3"]),
    "A12": dict(category="billable", minutes=60, billed=60, amount=5000, value=5000, clauses=["4.2"]),
    "A13": dict(category="goodwill", minutes=10, billed=15, amount=0, value=1250, rules=["G2"], counts=False),
    "A14": dict(category="no_work_logged", minutes=0, billed=0, amount=0, value=0),
    "B01": dict(category="included", minutes=60, amount=0, value=0, round=1),
    "B02": dict(category="included", minutes=30, amount=0, value=0),
    "B03": dict(category="goodwill", minutes=10, amount=0, value=1250, rules=["G1"], favour=1),
    "B04": dict(category="included", minutes=60, amount=0, value=0, round=2),
}
NOT_REQUESTS = ["N01", "N02"]
TOTALS = {"acme": dict(billable_pence=48750, billable_lines=5, goodwill_pence=3750, goodwill_lines=3),
          "bright-bakery": dict(billable_pence=0, billable_lines=0)}
HEALTH = {"acme": dict(hours_total=14.92, hours_in_scope=4.50, hours_beyond_scope=10.42, share=69.8, badge="Over scope"),
          "bright-bakery": dict(share=6.3, badge="Healthy")}
PERIOD = "2026-10"


def gbp(p):
    return f"£{p / 100:.2f}"


def check_decision(sid, exp, req, dec, favour_no):
    problems = []
    if dec is None:
        return ["no decision"]
    if dec.category != exp["category"]:
        problems.append(f"category {dec.category} (expected {exp['category']})")
    if dec.minutes_logged != exp["minutes"]:
        problems.append(f"minutes logged {dec.minutes_logged} (expected {exp['minutes']})")
    if "billed" in exp and dec.minutes_billed != exp["billed"]:
        problems.append(f"minutes billed {dec.minutes_billed} (expected {exp['billed']})")
    if dec.amount_pence != exp["amount"]:
        problems.append(f"amount {gbp(dec.amount_pence)} (expected {gbp(exp['amount'])})")
    if dec.value_pence != exp["value"]:
        problems.append(f"value {gbp(dec.value_pence)} (expected {gbp(exp['value'])})")
    for c in exp.get("clauses", []):
        if c not in dec.clause_refs:
            problems.append(f"clause {c} not cited (got {dec.clause_refs})")
    if exp.get("any_clauses") and not set(exp["any_clauses"]) & set(dec.clause_refs):
        problems.append(f"none of clauses {exp['any_clauses']} cited (got {dec.clause_refs})")
    for r in exp.get("rules", []):
        if r not in dec.rule_refs:
            problems.append(f"rule {r} not cited (got {dec.rule_refs})")
    if "round" in exp and req.revision_round != exp["round"]:
        problems.append(f"revision round {req.revision_round} (expected {exp['round']})")
    if "counts" in exp and dec.counts_towards_allowance != exp["counts"]:
        problems.append(f"counts towards allowance {dec.counts_towards_allowance} (expected {exp['counts']})")
    if "favour" in exp and favour_no != exp["favour"]:
        problems.append(f"favour number {favour_no} (expected {exp['favour']})")
    return problems


def compare(session):
    results = {"acme": [], "bright-bakery": []}
    clients = {c.slug: c for c in session.exec(select(Client)).all()}
    favour_counter = {}
    for sid, (source, ext) in SOURCE_IDS.items():
        slug = "bright-bakery" if sid.startswith("B") else "acme"
        item = session.exec(select(SourceItem).where(SourceItem.source == source, SourceItem.external_id == ext)).first()
        if item is None:
            results[slug].append((sid, False, "source item missing"))
            continue
        reqs = session.exec(select(Request).where(Request.source_item_id == item.id)).all()
        if sid in NOT_REQUESTS:
            ok = not reqs
            results[slug].append((sid, ok, "not a request" if ok else f"{len(reqs)} request(s) extracted: "
                                  + "; ".join(r.summary for r in reqs)))
            continue
        exp = EXPECTED[sid]
        if len(reqs) != 1:
            results[slug].append((sid, False, f"expected 1 request, got {len(reqs)}: " + "; ".join(r.summary for r in reqs)))
            continue
        req = reqs[0]
        dec = session.exec(select(Decision).where(Decision.request_id == req.id)).first()
        favour_no = None
        if dec is not None and dec.category == "goodwill" and dec.counts_towards_allowance:
            favour_counter[slug] = favour_counter.get(slug, 0) + 1
            favour_no = favour_counter[slug]
        problems = check_decision(sid, exp, req, dec, favour_no)
        got = (f"{dec.category}, {dec.minutes_logged}->{dec.minutes_billed} min, {gbp(dec.amount_pence)} / "
               f"{gbp(dec.value_pence)}, clauses {dec.clause_refs}, rules {dec.rule_refs}") if dec else "no decision"
        results[slug].append((sid, not problems, got if not problems else "; ".join(problems) + f"  [got: {got}]"))

    entry = session.exec(select(TimeEntry).where(TimeEntry.client_id == None)).all()  # noqa: E711
    n03 = [e for e in entry if e.description == "Portfolio site update"]
    ok = len(n03) == 1 and n03[0].request_id is None
    results["acme"].append(("N03", ok, "unassigned and ignored" if ok else f"found {len(n03)} entries, request_id "
                            f"{[e.request_id for e in n03]}"))

    extra = []
    for slug, exp in TOTALS.items():
        client = clients[slug]
        decs = [d for d in session.exec(select(Decision).where(Decision.period == PERIOD)).all()
                if session.get(Request, d.request_id).client_id == client.id]
        billable = [d for d in decs if d.category == "billable"]
        goodwill = [d for d in decs if d.category == "goodwill"]
        got_b, got_g = sum(d.amount_pence for d in billable), sum(d.value_pence for d in goodwill)
        ok = got_b == exp["billable_pence"] and len(billable) == exp["billable_lines"]
        if "goodwill_pence" in exp:
            ok = ok and got_g == exp["goodwill_pence"] and len(goodwill) == exp["goodwill_lines"]
        extra.append((f"{slug} totals", ok, f"billable {gbp(got_b)} ({len(billable)} lines), goodwill {gbp(got_g)} "
                      f"({len(goodwill)} lines)"))
        h = compute_health(decs)
        eh = HEALTH[slug]
        hok = h.beyond_scope_share_pct == eh["share"] and h.badge == eh["badge"]
        for key in ("hours_total", "hours_in_scope", "hours_beyond_scope"):
            if key in eh:
                hok = hok and round(getattr(h, key), 2) == eh[key]
        extra.append((f"{slug} health", hok, f"total {h.hours_total:.2f} h, in scope {h.hours_in_scope:.2f} h, beyond "
                      f"{h.hours_beyond_scope:.2f} h, share {h.beyond_scope_share_pct}%, badge {h.badge}"))
    return results, extra


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-run", action="store_true", help="compare the current database without running the pipeline")
    args = parser.parse_args()
    status = llm_key_status()
    if not status.ok:
        print(f"SKIPPED: {status.message}. The acceptance test needs the LLM (extraction, scope checks).")
        return 2
    init_db()
    if not args.no_run:
        # Same steps as `make seed` (demo clock, start period, files, pipeline). Idempotent: only new work runs.
        _, report, seconds = await seed()
        print(f"pipeline run: {report.decisions_made} new decisions in {seconds:.1f} s")
        for e in report.errors:
            print("PIPELINE ERROR:", e)
    with session_scope() as session:
        results, extra = compare(session)
    await cognee_client.wait_for_background_tasks()
    for slug in ("acme", "bright-bakery"):
        print(f"\n== {slug} ({PERIOD}) ==")
        for sid, ok, detail in results[slug]:
            print(f"{'PASS' if ok else 'FAIL'}  {sid}  {detail}")
    print("\n== totals and health ==")
    for name, ok, detail in extra:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    acme_ok = sum(ok for _, ok, _ in results["acme"])
    bakery_ok = sum(ok for _, ok, _ in results["bright-bakery"])
    bakery_decisions = [r for r in results["bright-bakery"] if r[0].startswith("B")]
    extra_ok = sum(ok for _, ok, _ in extra)
    print(f"\nSUMMARY: Acme {acme_ok}/{len(results['acme'])} (13 decisions + N01, N02, N03), "
          f"Bright Bakery {bakery_ok}/{len(bakery_decisions)} decisions, totals/health {extra_ok}/{len(extra)}")
    all_ok = acme_ok == len(results["acme"]) and bakery_ok == len(bakery_decisions) and extra_ok == len(extra)
    print("ACCEPTANCE PASSED" if all_ok else "ACCEPTANCE FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
