# Tab: Build Report

## 1. Summary
- Overall status: **partial (built, awaiting keys)**. Everything in PLAN.md is built. Only the parts that can run without an API key were run and verified. `.env` holds placeholder values: `LLM_API_KEY` is 6 characters starting `sk-`, and `STRIPE_SECRET_KEY` is 11 characters starting `sk_test_`. Tab treats both as missing. No Cognee, LLM or Stripe call has been made, and no result was faked or mocked.
- What works end to end today, without keys:
  - `make reset && make seed && make dev` from the repo. Reset wipes SQLite and runs `cognee.forget(everything=True)`, which succeeded on an empty store. Seed loads every demo file and routes it to the right client. The API and web app start and show clear "LLM key missing" and "Stripe key missing" banners instead of data that doesn't exist.
  - Ingestion matches the Phase 1 counts exactly (unit test `test_phase1_counts`), including the single unassigned time entry (N03) and the goodwill rules routed into both client datasets.
  - All deterministic logic is unit-tested, 71 tests passing: money maths and 15-minute rounding, meeting counting, the goodwill allowance and typo rule, routing, the London-time period and demo clock logic, the duplicate-invoice guard (including "a failed run is never retried"), the `sk_test_` guard, contract clause parsing, and the health numbers.
  - The calendar-to-meeting requests (no LLM needed) and the "Simulated" message flow work. Simulated messages are stored, labelled, and paused with a clear "key missing" message.
  - Every page renders against the no-key state. I checked Overview, Client, Settings and Memory with headless Chrome screenshots.
- Time spent per phase (approximate, about 40 minutes of wall time in total): Phase 0 (setup, docs, versions) ~8 min · Phase 1 (demo data, connectors, routing) ~7 min · Phases 2–4, 6, 7 backend code ~12 min · unit tests ~4 min · Phase 5 frontend ~8 min · README and report ~3 min.

## 2. Environment
- OS: macOS (Darwin 25.6.0, arm64)
- Python 3.12.11 (installed with `uv python install 3.12`; venv at `backend/.venv` via `uv sync`)
- Node v25.9.0, npm 11.12.1
- cognee **1.6.4**
- stripe (Python) **16.0.0**, pinned API version `2026-09-30.endive`
- Also: fastapi 0.143.2, sqlmodel 0.0.48, litellm 1.96.2, pydantic 2.14.1, icalendar 7.3.0, pypdf 6.20.1, fpdf2 2.8.9. Frontend: React 19.3.1, Vite 8.3.4, Tailwind CSS 4.3.3, TypeScript 5.9.3, react-router-dom 7.18.4.
- LLM provider and model: OpenAI through Cognee's defaults, as you asked (installed defaults: `openai/gpt-5.6-luna`, embeddings `openai/text-embedding-3-large`). **Not exercised yet: no key.**

## 3. Phase checklist
| Phase | Status (done / partial / not started / blocked) | Check result | Notes |
|---|---|---|---|
| 0 Setup | built, awaiting keys | Repo structure, `.gitignore` (with `.env`), `.env.example`, Makefile, README, Python 3.12 env and all dependencies done. Smoke tests written (`scripts/smoke_cognee.py`, `scripts/smoke_stripe.py`), **not run** as instructed. | Versions recorded in section 2. Cognee agent skills installed (`.agents/skills`, linked from `.claude/skills`). |
| 1 Demo data + ingestion | partial (counts ✅; memory part awaiting keys) | `test_phase1_counts` passes: Acme 1 contract, Sep 2 emails + 1 time entry, Oct 8 Slack / 4 emails / 3 calendar / 9 time entries; Bright Bakery 1 contract, 3 emails, 1 calendar, 3 time entries; 1 unassigned (N03); G1 routed to both datasets, G2 to Acme. `remember()` code written, not run. **Pending:** "remembered into both datasets" and the recall "What did Anna ask for on 22 October?" (`make phase1`). | Contract PDFs rendered from the .md with `scripts/render_contracts.py`; clause parsing from the PDF is tested. |
| 2 Terms and rules | built, awaiting keys | Not run. `make phase2` checks every required term against section 11, plus G1/G2 params. | The deterministic validation of LLM output is unit-tested. |
| 3 The brain | built, awaiting keys | `make acceptance` not run (needs the LLM). | Extraction, time matching, decisions, explanations, decision write-back all written. Deterministic parts tested. |
| 4 Stripe billing | built, awaiting keys | Not run. `make billing-check` / `make pay-check` written. | Duplicate guard and "failed run never retried" are unit-tested; demo clock tested. Payment status by polling (no webhook secret); the webhook endpoint is also built. |
| 5 Dashboard | partial | All pages built (Overview, Client, Ask Tab, Memory, Invoice, Proof, Settings). Typecheck and build clean. Four pages checked by screenshot in the no-key state. **Pending:** "every number matches the database" and "Why? works on every card" need decisions; the Invoice and Proof pages have no data to render yet. | Dark mode skipped (optional in PLAN.md). |
| 6 Proof page + disputes | built, awaiting keys | Not run. `make phase6` checks the proof link on the Stripe invoice, the Careers dispute (upheld, cites 2.1 and the 22 Oct email) and the phone-call dispute (escalated). | The precondition logic is unit-tested. |
| 7 Health report | built, awaiting keys | Number logic and badge thresholds unit-tested on synthetic decisions. The real Acme/Bright Bakery numbers are checked by `make acceptance`. | Narrative is LLM plus a number-whitelist check (unit-tested). |
| 8 Live sources | not tested | Slack (`conversations.history`) and IMAP pollers written; no credentials. | Settings shows "Live" only after a successful poll. |
| 9 Polish + demo readiness | partial | Without keys: `make reset` 4.2 s, `make seed` 0.3 s (files only). README with setup, env vars, commands and demo script done. **Pending:** full seed time with keys. | |

## 4. Acceptance results
- `make acceptance` was **not run**: it needs `LLM_API_KEY` (request extraction and scope checks are LLM calls). Without a key it prints `SKIPPED: LLM key missing ...` and exits 2. No output can be pasted yet.
- Accuracy: pending. The script prints X / 16 Acme checks (13 decisions + N01, N02, N03) and Y / 4 Bright Bakery decisions, plus totals (£487.50 / 5 lines, £37.50 / 3 goodwill lines) and the health numbers from section 13.3.
- Mismatches: none known yet. The expected table lives only in `backend/scripts/acceptance.py`, copied from PLAN.md section 13 without changes.
- Real output of `make test` (the part that can run now):
  ```
  cd backend && .venv/bin/python -m pytest -q
  .......................................................................  [100%]
  71 passed in 0.33s
  ```
  (test_money 17, test_goodwill 12, test_config 10, test_routing 6, test_terms_and_rules 6, test_meetings 5, test_clock 4, test_invoicing 4, test_misc 4, test_ingest 3)

## 5. Stripe results
- No Stripe calls yet (the key is a placeholder). No invoice id, total or line count to report. Whether Stripe accepts £0 invoice items is unknown. If it rejects them, the code moves goodwill lines to the invoice footer and records a note (PLAN.md 9.1 step 5).
- Parameters checked against the docs and the installed library (16.0.0): `InvoiceItem.create(customer, invoice, currency, amount, description, metadata)`, `Invoice.create(customer, collection_method="send_invoice", days_until_due, currency, description, metadata, custom_fields)`. Custom fields allow a name up to 40 characters, a value up to 140, and at most 4 fields; the proof URL is about 60 characters. Also `Invoice.finalize_invoice`, `send_invoice`, `pay(payment_method=...)` (the payment method must belong to the customer, so `pm_card_visa` is attached first), `Webhook.construct_event`, and `stripe.InvalidRequestError` / `StripeError` / `SignatureVerificationError`.
- Payment status: polling every 60 s (no `STRIPE_WEBHOOK_SECRET`, as you asked). The webhook endpoint is built but returns 400 while no secret is set. Not verified yet.

## 6. Cognee usage
- Datasets: `client_acme`, `client_bright-bakery`. Node sets: `contract`, `goodwill_rules`, `slack`, `email`, `calendar`, `timelog`, `decision`, `invoice`, `dispute`, plus `simulated` (each together with the client slug). `remember()` is batched per client per source. Goodwill rules are remembered into every client dataset they apply to.
- `self_improvement=False` (PLAN.md default; `TAB_COGNEE_SELF_IMPROVEMENT=true` turns it on). Seeding time: **pending** (it needs the key; `make seed` prints it).
- Local stores: `backend/.cognee/` (`DATA_ROOT_DIRECTORY` and `SYSTEM_ROOT_DIRECTORY`), gitignored.
- Differences from PLAN.md section 7 and the docs, found in the installed 1.6.4 source:
  1. **`RecallPreconditionError` is not an importable class.** It is a `cognee.exceptions.CogneeValidationError` whose `.name == "RecallPreconditionError"`. The wrapper catches it that way.
  2. **On an empty or failed graph, `recall()` does not raise.** It returns one `source="system"` item with `status="memory_warming_up"` or `"build_failed"`. The wrapper turns this into a clear "memory empty" error, so a marker is never used as context.
  3. `recall()` may append `source="skills"` items to procedural-sounding queries (the skill gate). Tab only uses `source="graph"` items and sets `SKILL_GATE_ENABLED=false` by default.
  4. With caching on, `AUTO_FEEDBACK` (default true) adds one LLM call per answered recall. Tab sets `AUTO_FEEDBACK=false` by default (overridable in `.env`).
  5. Cognee looks for `.env` only up to the nearest `pyproject.toml` (that is `backend/`), so Tab sets `COGNEE_ENV_FILE` to the repo-root `.env`. Cognee logs that values in that file take precedence over variables already set in the environment.
  6. `visualize_graph(destination_file_path, ..., dataset=...)` renders **one dataset per call** and returns the HTML. The Memory page therefore has a client selector rather than one combined graph.
  7. The Cognee docs say scripts should call `await cognee.wait_for_background_tasks()` before exiting. The seed, acceptance, phase-check and smoke scripts do so.
  8. `cognee.forget(everything=True)` works with no data and no key. It returned `{'datasets_removed': 0, 'status': 'success'}`.
  9. Structured LLM calls go through `cognee.infrastructure.llm.LLMGateway.acreate_structured_output`. The default `litellm_native` backend tries OpenAI strict JSON-schema mode and falls back to non-strict if strict mode is rejected. Whether my schemas pass strict mode is unverified.

## 7. Deviations from the plan
1. **Extra columns** (all additive, marked "Not in PLAN.md" in `models.py`):
   - `GoodwillRule.parse_status` / `parse_note`: tells "not understood" apart from "not parsed yet because the key is missing".
   - `Request.is_future_work`: from the step-3 output schema.
   - `TimeEntry.matched_at`: avoids asking the LLM twice about the same entry.
   - `Decision.counts_towards_allowance`: G2 typo fixes don't use the allowance.
   - `Invoice.notes` and `remembered_at`: record Stripe fallbacks and whether the invoice was remembered.
   - `Dispute.outcome_reason` and `remembered_at`: Maya sees why a dispute was escalated; the client doesn't.
2. **Three extra contract-term keys:** `out_of_scope_clause`, `extra_revisions_clause` and `extra_meetings_clause`. They let decisions cite 2.4, 3.3 and 4.2 without hardcoding clause numbers, and are treated as required like the others (if any is missing, the client's decisions are put on hold and reported).
3. **The hourly-rate clause (5.2) is added to `clause_refs`** for billable and goodwill decisions. Billable line descriptions therefore read, for example, "… @ £50/h, clause 2.4, 5.2".
4. **Disputes are remembered after the reply**, not before (PLAN.md 10.3 lists save, remember, recall, reply). Building the graph would otherwise delay the reply well past "a few seconds". The remembered record includes the outcome.
5. **Placeholder detection:** a key that is very short or contains `xxx`, `...`, `your`, and so on is treated as missing. This is how the current `.env` is detected.
6. **`DATABASE_URL=sqlite:///./tab.db` resolves relative to `backend/`**, whatever the working directory.
7. **The repo root is the project root**, with no `tab/` subfolder.
8. **TypeScript 5.9 instead of the newest 7.x.** 7.x is a major rewrite and I didn't want to depend on it untested.
9. **Record formats:** time-entry records use `Text: N min logged: <description>`. Calendar records use `Meeting '<title>' on <date> from <start> to <end> (N min). Attendees: …`.
10. **`goodwill_rules.md` format:** each rule has an `## G1` heading and an `Applies to: all clients | <slug>` line, so who a rule applies to is parsed deterministically, never by the LLM.
11. **Bright Bakery contract wording** (section 11.2 only gave its terms; "same structure" as Acme). I wrote 2.2 "supplied as a print-ready PDF", 2.3 "fixes to errors in delivered designs are included for 30 days", 3.1 "feedback by email", and 5.1 a £900 fixed fee. I added no clause about price changes; B03 has to be judged from the general terms.
12. **The invoice event uses the full client name:** "Raised invoice for Acme Outdoor Ltd: £487.50, 5 billable lines, 3 favours".
13. **Overview shows the latest period up to "now" that has requests**, not strictly the calendar month of "now". After jumping to 1 Nov 09:00 it still shows October, the period just invoiced.
14. **Consistency guards return `needs_review` instead of guessing:**
    - the LLM says "in scope" but counts more revision rounds than the contract includes;
    - no valid contract clause was cited.
    Cited clause numbers that aren't in the contract are dropped.
15. **The billing job only runs with a Stripe key.** Without one it logs "Stripe key missing" once per closed period. It doesn't log "nothing to bill" then either.
16. **Only the health narrative is checked for invented numbers.** Decision explanations are prompted to use only the given facts but aren't number-checked, because dates and clause numbers make a strict check unreliable.
17. **Editing a goodwill rule** re-decides the current display period, but only for clients with no invoice for it. Decision records already in Cognee are not deleted (memory keeps the history).
18. **Cognee agent skills** were copied into `.agents/skills` and linked from `.claude/skills`, as the Cognee docs describe.

## 8. Unclear / needs decision
1. **Time-matching window** (8.2, "within −1 to +3 days of the entry date"). The direction is ambiguous. **Chosen:** the time entry date minus the request date is between −1 and +3 days (work is logged from 1 day before to 3 days after the request). **Alternative:** the literal reading, request date minus entry date between −1 and +3. Both give the same candidates for the demo data, since every entry is on its request's day.
2. **September history** ("for memory only, never billed in October"). **Chosen:** seed sets `tab_start_period = 2026-10`. Items before it are remembered in Cognee but never extracted, decided or billed, and the Client page shows them as "History". **Alternative:** decide September too. It would never be invoiced, since S01 is included and S02 has no time.
3. **Disputes on meeting lines** (10.3 requires "a matched time entry"). Meetings have no time entry (the calendar event is the time evidence). **Chosen:** the literal reading, so a dispute on the A12 meeting line is escalated to Maya. **Alternative:** count the calendar event as time evidence.
4. **How acceptance reads the "Clause / rule" column.** **Chosen:**
   - each listed clause or rule must be among the decision's cited refs (extra refs such as 5.2 are allowed);
   - "2.1 / 2.4" means at least one of them;
   - A09 "2.4 + G1 allowance used" means clause 2.4 is cited and G1 is in `rule_refs`; Tab cites the rule whose allowance ran out;
   - "round 2 / round 3" and Bright Bakery's "revisions round 1/2" are checked against `Request.revision_round`;
   - "favour 1 of 2" is checked by counting allowance favours in date order.
   **Alternative:** check only category and amounts.
5. **Health narrative and numbers:** "must not contain any number that isn't in the deterministic set". **Chosen:** it may use the listed numbers in any formatting, plus the percentage rounded to a whole number ("70%", as in the demo script). Anything else is rejected once, then the narrative is withheld with a note. **Alternative:** exact strings only.
6. **"Favours used" on the health panel:** **Chosen:** allowance favours only (Acme "2 of 2"), with always-free typo favours shown separately ("+1 typo fix, always free").
7. **An over-length meeting** (not in the demo): the health report counts its whole duration as beyond scope, while only the overrun is billed.
8. **The Stripe Customer idempotency key** is `tab-customer-<id>-<slug>`. If you reset within 24 hours, Stripe hands back the same test customer, which is harmless. Invoice and item keys use the invoice's random proof token, so re-billing after a reset is never blocked by a reused key.

## 9. Blockers and errors
1. **Blocker: no real API keys.** The `.env` values are placeholders, so `llm_key_status()` reports "LLM key missing: LLM_API_KEY in .env looks like a placeholder" and `stripe_key_status()` reports "Stripe key missing: STRIPE_SECRET_KEY in .env looks like a placeholder. Billing is disabled." Everything that needs them is built and waiting.
2. Contract PDF rendering, first attempt: `fpdf.errors.FPDFException: Not enough horizontal space to render a single character`. `multi_cell` left the cursor at the right margin. Fixed by passing `new_x="LMARGIN", new_y="NEXT"`.
3. My own probe, not app code: `FileNotFoundError: COGNEE_ENV_FILE=/dev/null does not name a file.` Cognee needs a real file, so I re-ran the probe with an empty file.
4. Unverified risks, listed so they aren't a surprise:
   - whether OpenAI accepts the response schemas in strict mode (Cognee falls back to non-strict automatically);
   - whether Stripe accepts `amount=0` invoice items (a fallback is built);
   - LLM accuracy on the 17 acceptance decisions.

## 10. Not done / pending
Prioritised:
1. Add the real keys, then run the Phase 0 smoke tests and record their output.
2. `make reset && make seed` with keys: record the seeding time and run the Phase 1 memory checks and the Phase 2 terms and rules checks.
3. `make acceptance`: record accuracy and every mismatch. Fix mismatches by improving prompts or logic, never by editing the expected table.
4. The Phase 4 billing check and the payment check.
5. The Phase 6 dispute checks.
6. Phase 5 with data: on-screen numbers against the database, "Why?" on every card, the Invoice and Proof pages rendered with a real invoice.
7. The Phase 7 narrative for Acme ("Over scope") and Bright Bakery ("Healthy").
8. Measure seeding with `self_improvement=True` against `False`.
9. Phase 8, live Slack and IMAP: **not tested** (no credentials, as agreed).
10. Dark mode (optional; skipped).
11. Nothing has been committed to git (you didn't ask). `.env`, `backend/.venv`, `backend/.cognee`, `backend/tab.db` and `frontend/node_modules` are gitignored.

## 11. How to run the demo
From a clean clone:
```bash
cp .env.example .env    # set LLM_API_KEY (OpenAI) and STRIPE_SECRET_KEY (sk_test_...)
make setup
make reset && make seed && make dev
# open http://localhost:5173 and follow the demo script in README.md
```
Known issues:
- Without keys the app runs, but there are no decisions, invoices, Ask Tab answers or graph, and each place says why.
- `make seed` makes many LLM calls: Cognee graph building per batch, about 15 extractions, about 15 time matches, 17 scope checks and explanations. Expect minutes, not seconds; the time is pending measurement.
- Don't run `make seed` while `make dev` is running. Both write to the same local Cognee stores; use Settings, "Reset demo" instead.
- Phase 6 checks and manual disputes leave dispute rows. Run `make reset && make seed` before recording.

## To run once keys are added
Run in this order from the repo root (`make dev` stopped):
```bash
# 0. Put the real keys in .env: LLM_API_KEY=sk-... (OpenAI) and STRIPE_SECRET_KEY=sk_test_...

# 1. Phase 0 smoke tests (expect PASS from both; output lists cognee/stripe/python versions)
make smoke-cognee
make smoke-stripe

# 2. Fresh seed (prints remember() time and total seed time)
make reset && make seed

# 3. Phase 1 and 2 checks
make phase1
make phase2

# 4. Acceptance (PLAN.md section 13); paste the full output into REPORT.md section 4
make acceptance

# 5. Phase 4 billing: jumps the demo clock to 2026-11-01 09:00 and verifies Stripe;
#    then pays it with the test card through the API and checks Tab marks it paid
make billing-check
make pay-check

# 6. Phase 6: proof link on the Stripe invoice, Careers dispute upheld, phone-call dispute escalated
make phase6

# 7. Phases 5 and 7 by hand, then reset for a clean demo
make reset && make seed && make dev   # check the pages; on 1 Nov the invoice is raised again in Stripe test mode
```
Checks still pending (all need keys unless marked):
- Phase 0: Cognee remember/recall round trip; Stripe test Customer create and delete.
- Phase 1: every source item remembered in its client dataset; goodwill rules remembered into both datasets; recall "What did Anna ask for on 22 October?" mentions the Careers page.
- Phase 2: all required ContractTerm keys for both clients with the section 11 values; G1 and G2 parsed correctly.
- Phase 3: `make acceptance` (16 Acme checks, 4 Bright Bakery decisions, totals, health numbers).
- Phase 4: exactly one Acme invoice of £487.50 with 5 billable and 3 goodwill lines; no Bright Bakery invoice; a second run creates nothing; whether £0 lines were accepted; paid status reaches Tab by polling.
- Phase 5: every number on screen matches the database; "Why?" works on every card; Invoice and Proof pages render with real data.
- Phase 6: the Stripe proof link opens the page; Careers dispute upheld, citing 2.1 and the 22 Oct email; "Maya told me on the phone it was free" escalated.
- Phase 7: Acme 14.92 h / 4.50 h / 10.42 h / 69.8%, badge "Over scope"; Bright Bakery 6.3%, "Healthy"; narrative written without invented numbers.
- Phase 8: live Slack message decided within 60 s. **Not tested: no credentials** (as agreed).
- Phase 9: full `make reset && make seed` time with keys.
