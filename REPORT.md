# Tab: Build Report

## 1. Summary
- Overall status: **partial, demo-ready.** The full pipeline ran with real keys. Tab raised the Acme invoice of **£487.50** in Stripe test mode with 5 billable lines and 3 £0 "On the house" lines, and no Bright Bakery invoice, as PLAN.md requires.
- Acceptance (read-only scoring of the seeded database): **Acme 15/16, Bright Bakery 2/4**, totals 2/2, health 0/2. The model is gpt-5-nano, the cheapest available.
- What works end to end:
  - **Ingestion and memory.** Demo files are routed to clients. Every client source item is remembered in Cognee, in per-client datasets with node sets.
  - **Contract and rules.** Contract terms are extracted with clause references (Phase 2: **51/51**). G1 and G2 are parsed correctly.
  - **Decisions.** 20 decisions, each with an explanation, evidence and "What Tab remembered", written back to Cognee.
  - **Billing.** The billing job raised exactly one Acme invoice, finalized and sent. Stripe accepted the £0 lines and the "Proof of work" custom field. The second run created nothing new.
  - **Dashboard and proof page.** They render with real data (checked by screenshot). The Overview page has a Billing policy card.
- Not yet verified with real keys:
  - disputes (left for the video);
  - Ask Tab;
  - the Memory graph render;
  - the health narrative;
  - payment status turning "paid" (you'll pay on camera).
- Time: building took about 40 min (first session). With real keys: the smoke tests took about 2 min. `make reset && make seed` took **30.6 min** but produced 0 decisions because of the terms bug in section 9. The incremental pipeline run after the fix took **15.9 min**. The billing check took about 1 min.

## 2. Environment
- macOS (Darwin 25.6.0, arm64), Python 3.12.11 (uv), Node v25.9.0, npm 11.12.1
- cognee **1.6.4**; stripe (Python) **16.0.0**, API version `2026-09-30.endive`
- Frontend: React 19.3.1, Vite 8.3.4, Tailwind CSS 4.3.3, TypeScript 5.9.3
- **LLM: `openai/gpt-5-nano`** (`LLM_PROVIDER=openai`, `LLM_MODEL=openai/gpt-5-nano`)
  - Price: $0.05 per 1M input tokens, $0.005 cached, $0.40 per 1M output tokens.
  - It is the cheapest text model on OpenAI's pricing page (developers.openai.com/api/docs/pricing, 15 Oct 2026). Its model page lists `structured_outputs`, and the key has access to it.
  - The `openai/` prefix matches Cognee's default model name (`openai/gpt-5.6-luna`). Cognee confirmed it reads `openai openai/gpt-5-nano`.
- Embeddings: Cognee default `openai/text-embedding-3-large` (unchanged)
- Stripe account: `acct_1UQtEZFyqsEONG0f` (test mode, "sidebus sandbox")

## 3. Phase checklist
| Phase | Status | Check result | Notes |
|---|---|---|---|
| 0 Setup | done | `make smoke-cognee` PASS: remember 60.3 s, recall 2.8 s, answer "The Careers page (for Acme Outdoor Ltd)." `make smoke-stripe` PASS: created and deleted `cus_VRnTlJHD4xA1BD`, livemode False. | Versions in section 2. |
| 1 Demo data + ingestion | done (one check not run) | Counts unit test passes. **All 39 client source items remembered:** acme contract 1, slack 8, email 6, calendar 3, timelog 10, goodwill_rules 2; bright-bakery contract 1, email 3, calendar 1, timelog 3, goodwill_rules 1. | The recall check "What did Anna ask for on 22 October?" was **not run** (`make phase1`), to avoid touching Cognee's stores while the API runs. The smoke test shows the same kind of recall working. |
| 2 Terms and rules | done | `make phase2`: **51/51 PASS** (every required term and value from section 11, clause refs, G1 and G2). | Needed one fix: a retry when the model omits keys (section 9). |
| 3 The brain | partial | Acceptance Acme 15/16, Bright Bakery 2/4 (section 4). | 20 decisions, 0 errors. |
| 4 Stripe billing | done (payment pending) | One Acme invoice of £487.50, 8 Stripe lines (5 billable, 3 at £0), no Bright Bakery invoice. The second run created nothing; Stripe has exactly 1 invoice for the customer and period. | `make billing-check` crashed **after** these checks on a bug in the check script itself (fixed). Payment is left for the video; `make pay-check` was not run, as you asked. |
| 5 Dashboard | done (spot-checked) | The Overview stats match the database (£487.50 recovered, 3 favours worth £37.50, 0 needs review, 1 invoice raised). Acme page and proof page checked by screenshot. | Not every "Why?" panel was opened one by one. Billing policy card added. |
| 6 Proof page + disputes | partial | The proof page renders with all 8 lines; the Stripe invoice carries the proof link (custom field and description). | Dispute checks (`make phase6`) **not run**, so the disputes you make on camera are the first. |
| 7 Health report | partial | Badges correct: Acme "Over scope", Bright Bakery "Healthy". The numbers differ from 13.3 because of the matching misses (section 4). | The narrative ("Write recommendation") was not generated. |
| 8 Live sources | not tested | No credentials, as agreed. | |
| 9 Polish + demo readiness | done | Seed time measured (section 6); README updated. | |

## 4. Acceptance results
`make acceptance` re-runs the pipeline, so per your instruction it was **not** run that way. The same script was run as `scripts/acceptance.py --no-run`, which scores the decisions already in the database with **no LLM calls**:
```
== acme (2026-10) ==
FAIL  A02  expected 1 request, got 2: Tighten the headline on the Home page to 'Gear up for every trail'.; Change the main button colour on the Home page to forest green (#2F5D3A).
PASS  A03  billable, 90->90 min, £75.00 / £75.00, clauses ['3.2', '3.3', '5.2', '5.3'], rules []
PASS  A04  goodwill, 15->15 min, £0.00 / £12.50, clauses ['2.4', '5.2', '5.3', '5.4'], rules ['G1']
PASS  N01  not a request
PASS  A05  billable, 180->180 min, £150.00 / £150.00, clauses ['2.4', '5.2', '5.3', '5.4'], rules []
PASS  A06  included, 60->0 min, £0.00 / £0.00, clauses ['4.1'], rules []
PASS  N02  not a request
PASS  A07  goodwill, 15->15 min, £0.00 / £12.50, clauses ['2.4', '5.2', '5.3', '5.4'], rules ['G1']
PASS  A08  included, 60->0 min, £0.00 / £0.00, clauses ['4.1'], rules []
PASS  A09  billable, 15->15 min, £12.50 / £12.50, clauses ['2.4', '5.2', '5.3', '5.4'], rules ['G1']
PASS  A10  billable, 240->240 min, £200.00 / £200.00, clauses ['2.4', '5.2', '5.3', '5.4'], rules []
PASS  A11  included, 30->0 min, £0.00 / £0.00, clauses ['2.3'], rules []
PASS  A12  billable, 60->60 min, £50.00 / £50.00, clauses ['4.2', '5.2'], rules []
PASS  A13  goodwill, 10->15 min, £0.00 / £12.50, clauses ['2.4', '5.2', '5.3', '5.4'], rules ['G2']
PASS  A14  no_work_logged, 0->0 min, £0.00 / £0.00, clauses [], rules []
PASS  N03  unassigned and ignored
== bright-bakery (2026-10) ==
FAIL  B01  expected 1 request, got 3: Move the pastries section to the first page.; Make the prices a bit larger, people at the back of the queue can't read them.; Use the darker brown from the logo for headings.
PASS  B02  included, 30->0 min, £0.00 / £0.00, clauses ['4.1'], rules []
FAIL  B03  category included (expected goodwill); value £0.00 (expected £12.50); rule G1 not cited (got []); favour number None (expected 1)  [got: included, 10->0 min, £0.00 / £0.00, clauses ['2.1', '3.2'], rules []]
PASS  B04  included, 60->0 min, £0.00 / £0.00, clauses ['2.1', '3.2'], rules []
== totals and health ==
PASS  acme totals  billable £487.50 (5 lines), goodwill £37.50 (3 lines)
FAIL  acme health  total 12.92 h, in scope 2.50 h, beyond 10.42 h, share 80.6%, badge Over scope
PASS  bright-bakery totals  billable £0.00 (0 lines), goodwill £0.00 (0 lines)
FAIL  bright-bakery health  total 1.67 h, in scope 1.67 h, beyond 0.00 h, share 0.0%, badge Healthy
SUMMARY: Acme 15/16 (13 decisions + N01, N02, N03), Bright Bakery 2/4 decisions, totals/health 2/4
ACCEPTANCE FAILED
```
- Accuracy: **Acme 15/16, Bright Bakery 2/4.** The money is fully correct for both clients.
- Mismatches:

| ID | Expected | Got | Likely reason |
|---|---|---|---|
| A02 | 1 included request (round 2), 120 min | Split into 2 requests (headline, button colour), both "No time logged" | gpt-5-nano split one feedback email into its bullet points. The 120-min entry ("Home page revisions round 2") was then matched at confidence 0.60, below the 0.7 bar, so it was left unmatched (shown in the feed and on the client page). Money is unaffected, since it would have been £0. |
| B01 | 1 included request (round 1), 60 min | Split into 3 requests, all "No time logged" | Same as A02 (match confidence 0.40). |
| B03 | goodwill (G1), worth £12.50 | included, clauses 2.1 and 3.2 | The model judged the croissant price change part of the menu revision allowance. PLAN.md says it is a content update, not a revision round. A model-quality miss; no invoice either way. |
| Acme health | 14.92 h / 4.50 h / 69.8% | 12.92 h / 2.50 h / 80.6% | Consequence of A02: its 120 min are not counted. The badge is still "Over scope". |
| Bright Bakery health | 6.3% | 0.0% | Consequences of B01 (60 min not counted) and B03 (counted as included). The badge is still "Healthy". |

- Your rule was "switch back to the default model if fewer than 12/16 Acme". Acme scored 15/16, so gpt-5-nano was kept. Per your later instruction there was no reset or reseed, so no attempt was made to improve the Bright Bakery results. The expected table was not edited.
- `make test`: 71 passed.

## 5. Stripe results
- Invoice **`in_1UQudoFyqsEONG0f7qVy94Hp`**, customer `cus_VRoGIrUE9yr7kA` for Acme Outdoor Ltd, status **open**, total **£487.50 GBP** (Stripe `total=48750`), test mode.
- **8 lines:** 5 billable (£75.00, £150.00, £12.50, £200.00, £50.00) and 3 at **£0**. **Stripe accepted the £0 invoice items**; the footer fallback was not needed, and the footer is empty.
- The "Proof of work" custom field was accepted: `http://localhost:5173/proof/VmjSOC8URRmnAhcu91TP7hKLGNRd5HFa`. The link is also in the invoice description.
- Hosted invoice: https://invoice.stripe.com/i/acct_1UQtEZFyqsEONG0f/test_YWNjdF8xVVF0RVpGeXFzRU9ORzBmLF9WUm9HQjlkSGZUcFNQMzdpWmlrQ1gwUzFZVFBETjVULDE4MjYzNDU4Nw0200XE4s3daw?s=ap
- No Bright Bakery invoice. The second billing run created nothing (1 Tab invoice row; 1 Stripe invoice for the customer and period).
- Payment status: polling every 60 s (no webhook secret). **Not yet observed turning "paid"**: you'll pay on camera with 4242 4242 4242 4242.

## 6. Cognee usage
- Datasets `client_acme` and `client_bright-bakery`. Node sets used: contract, goodwill_rules, slack, email, calendar, timelog, decision (14 Acme and 6 Bright Bakery decisions written back), invoice (1).
- `self_improvement=False`. **Seeding:**
  - 11 `remember()` batches took **1,442.6 s** (about 2–2.5 min per batch with gpt-5-nano); the whole seed took 1,838.1 s.
  - The incremental run (terms retry, 20 decisions, decision write-back) took 952.8 s.
  - I did not measure `self_improvement=True`; it would only be slower.
- Differences from PLAN.md section 7 (unchanged from the first report):
  1. `RecallPreconditionError` is a `CogneeValidationError` with that `.name`, not an importable class.
  2. An empty graph returns a `source="system"` "memory_warming_up" marker instead of raising.
  3. A skill gate can append `source="skills"` items to answers; disabled here.
  4. `AUTO_FEEDBACK` adds an extra LLM call per recall; disabled here.
  5. Cognee's `.env` lookup stops at `backend/pyproject.toml`, so Tab sets `COGNEE_ENV_FILE`.
  6. `visualize_graph` renders one dataset per call.
  7. Scripts must call `wait_for_background_tasks()` before exiting.
  8. Tab's structured LLM calls go through Cognee's `LLMGateway`. With gpt-5-nano this works: every terms, extraction, matching, scope and explanation call returned a valid result.

## 7. Deviations from the plan
Unchanged from the first report:
1. Extra columns, all additive: rule parse status, `is_future_work`, `matched_at`, `counts_towards_allowance`, invoice notes and `remembered_at`, dispute `outcome_reason`.
2. Extra required term keys `out_of_scope_clause`, `extra_revisions_clause` and `extra_meetings_clause`.
3. The rate clause, and here often 5.3 and 5.4 as well, appears in `clause_refs`, so line descriptions read "clause 2.4, 5.2, 5.3, 5.4".
4. Disputes are remembered after the reply.
5. Placeholder-key detection.
6. The SQLite path resolves relative to `backend/`.
7. The repo root is the project root.
8. TypeScript 5.9.
9. Record formats for time entries and calendar events.
10. `goodwill_rules.md` has an "Applies to:" line.
11. Bright Bakery contract wording.
12. The invoice event uses the full client name.
13. Overview shows the latest period with requests.
14. Consistency guards return `needs_review`.
15. The billing job needs a Stripe key.
16. Only the health narrative is checked for invented numbers.
17. Rule edits re-decide un-invoiced periods only.
18. Cognee skills installed in `.agents/skills`.

New in this session:

19. **Terms extraction retries once** when required keys are missing, telling the model which keys it left out. Nothing is defaulted; if keys are still missing, decisions stay on hold as before.
20. **The pipeline was finished with an incremental run** (`run_pipeline` on the existing database, a one-off script in the session scratchpad), not a second `make seed`. Memory and ingestion were kept.
21. **Billing policy card** on the Overview page (static text describing existing guardrails; no new logic).
22. **Demo state differs from "31 Oct 18:00, no invoice"**, per your change of plan: the demo clock is at **1 Nov 09:00** and the Acme invoice is already raised (open, unpaid).

## 8. Unclear / needs decision
Unchanged from the first report:
1. Time-matching window direction (chose entry − request ∈ [−1, +3] days).
2. September is history only.
3. Disputes on meeting lines are escalated (no time entry).
4. How acceptance reads the clause and rule columns.
5. Health narrative number rounding.
6. "Favours used" counts allowance favours only.
7. Over-length meetings in the health report.
8. Idempotency keys.

New:

9. **Should one feedback message be one request?** gpt-5-nano splits multi-point feedback emails (A02, B01) into several requests, and then a single time entry can't cover all of them. **Current:** each split request is decided separately, so the unmatched ones show "No time logged". **Options:** tell the extraction prompt that one revision round is one request, or let a time entry cover several requests from the same message. Either needs a re-run of the pipeline.
10. **gpt-5-nano or the default model?** Acme scored 15/16, so it passed your threshold of 12. A stronger model would likely fix B03 and the splitting, at about 4x the price for gpt-5.6-luna.

## 9. Blockers and errors
1. **First seed: 0 decisions.** `terms_incomplete`: "Contract terms missing for Acme Outdoor Ltd: out_of_scope_examples. Decisions are on hold." The same happened for Bright Bakery.
   - Cognee's recall of the contract was correct.
   - gpt-5-nano returned null for that one key.
   - Fixed with the single retry (section 7, item 19). The incremental run then extracted 14 terms per client.
2. **`make billing-check` crashed after the invoice was raised and verified**: `AttributeError: 'get' is a dict method, but a StripeObject is not a dict.` The cause was `(i.metadata or {}).get(...)` in the check script. Fixed with `.to_dict()`. I didn't re-run it (you asked for one run); I verified the remaining checks read-only (section 5). The same pattern was fixed in `phase_checks.py` (custom fields).
3. **The Settings page showed Stripe as "Error"** because of the same `.get()` pattern in `account_summary()`. Fixed; it now shows "Test mode connected · acct_1UQtEZFyqsEONG0f".
4. Earlier errors (contract PDF rendering, `COGNEE_ENV_FILE=/dev/null`) are unchanged from the first report and were resolved then.

## 10. Not done / pending
1. Disputes on camera. The Careers line should be upheld; "Maya told me on the phone it was free" should be escalated. Neither has been verified yet.
2. Payment on camera, then watch polling turn the status "paid" within 60 s. Not yet observed.
3. Not exercised with keys yet: Ask Tab answers, the Memory graph render ("Refresh graph"), and the health recommendation paragraph.
4. `make phase1` (one recall) and `make phase6` were not run.
5. Improve B03, A02 and B01 (prompt change or a stronger model), then re-seed. Needs your decision (section 8).
6. Live Slack and IMAP: not tested.
7. Dark mode: skipped (optional).
8. Two cosmetic issues: the A14 card repeats "No time logged"; the model tagged the contact-form bug fix as "revision round 1".

## 11. How to run the demo
The current state is ready to record. `make dev` is running (API :8000, web :5173), the demo clock is at 1 Nov 09:00, and the Acme invoice is raised and open.
- Overview: http://localhost:5173
- Acme: http://localhost:5173/clients/acme
- Proof page: http://localhost:5173/proof/VmjSOC8URRmnAhcu91TP7hKLGNRd5HFa
- Stripe hosted invoice: section 5

From a clean clone: `cp .env.example .env` (set the keys), `make setup && make reset && make seed && make dev`.

Known issues:
- The seed takes about 45 min with gpt-5-nano.
- Don't run `make seed` while `make dev` is running.
- Settings, "Reset demo" wipes everything and re-seeds (another ~45 min), and a new invoice would be raised on the next jump to 1 Nov.
