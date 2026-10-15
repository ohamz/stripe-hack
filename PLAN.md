# Tab: Build Plan

> **One line:** Tab watches where a freelancer's work actually happens, keeps a fair tab with every client, gives credit for the favours the freelancer chooses to do, and automatically bills the rest through Stripe, with proof for every pound.

This document is the single source of truth for the build. If something here is unclear or contradicts itself, **stop and report it. Do not guess.**

---

## 0. How to read this plan

- **Section 1–3:** what we are building and why (product).
- **Section 4–9:** how it works (architecture, data, memory, logic, Stripe).
- **Section 10–11:** what the user sees (UI, demo data).
- **Section 12–14:** how to build it (phases, acceptance tests, run commands).
- **Section 15–16:** rules for the coding agent and the final report format.

Words used throughout:
- **Freelancer:** the user of Tab (demo persona: Maya Chen).
- **Client:** the freelancer's customer (demo: Acme Outdoor Ltd, Bright Bakery).
- **Source item:** one raw piece of evidence (a Slack message, an email, a calendar event, a time entry, a contract).
- **Request:** something a client asked the freelancer to do, extracted from a source item.
- **Decision:** Tab's verdict on a request: `included`, `goodwill`, `billable`, `needs_review` or `no_work_logged`.
- **Period:** a calendar month. The demo period is **October 2026**.

---

## 1. The problem and the pitch

**Problem:** A lot of freelance work goes unbilled: small requests here and there. A few of them is good and shows flexibility, but together they add up to hours of unpaid work. Just three 20-minute favours a week is over 4 hours of unpaid work a month. And when freelancers do bill extras, clients push back because they don't remember asking.

**Solution:** Tab reads the places work happens (Slack, email, calendar, time tracker, the contract), remembers everything per client in Cognee, decides what is included, what is a free favour and what is billable, and raises the Stripe invoice itself, with a proof page that shows the evidence for every line.

**Hackathon fit (Track 02: Agents that collect):**
| Requirement | How Tab meets it |
|---|---|
| Real-world trigger | Client messages (Slack, email), calendar events, time logs, and the contract |
| Real bill in Stripe test mode | Tab creates a Stripe Customer, Invoice and Invoice Items, finalizes and sends the invoice |
| No human raises the bill | A scheduled job raises the invoice on the 1st of the month (contract clause 5.4) |
| Side quest: Cognee central | Every decision depends on recalling the contract, the goodwill rules and the client's history from Cognee; every "why?" is answered from Cognee memory |

---

## 2. The three features (and what is NOT included)

1. **Goodwill ledger.** The freelancer writes simple rules in plain English (for example, "favours under 20 minutes are free, max 2 per client per month"). Tab tracks them and shows favours on the invoice as **£0 "On the house" lines**, so the client sees the value they got for free. When the allowance runs out, Tab starts billing.
2. **Proof page for every invoice.** Each Stripe invoice links to a page where the client can see the evidence behind each line (the message, the hours, the contract clause) and dispute a line. Tab answers disputes from memory.
3. **Client health report.** Per client: how much of the work this month was beyond scope, favours used, amount billed, and a one-paragraph recommendation (for example, "consider raising the rate at renewal").

**Explicitly NOT in scope** (do not build):
- Tab does **not** reply to clients in Slack or email in real time, and does not send quotes before work starts.
- No multi-user accounts or login. Single freelancer, local app.
- No live-mode Stripe. Test mode only.
- No mobile app.

---

## 3. Decisions already made (the user can change these; the agent must not)

| Decision | Choice | Why |
|---|---|---|
| Product name | **Tab** | Short, matches "keep a fair tab" |
| Backend | Python 3.12, FastAPI | Cognee is a Python library |
| App database | SQLite via SQLModel | Zero setup, enough for a demo |
| Memory | Cognee (Python SDK, local default stores) | Core of the product and the side quest |
| LLM | One provider for both Cognee and the app, configured by env vars (default: OpenAI, Cognee's default) | One key, fewer moving parts |
| Frontend | React + Vite + TypeScript + Tailwind CSS | Fast to build, looks good |
| Currency | GBP, all amounts stored as integer pence | Avoid float errors |
| Stripe | Python `stripe` library, test mode only | Required by the track |
| Live sources | Slack (optional, bot token) and email via IMAP (optional). Everything must work fully with demo files only | Demo must never depend on a flaky live connection |
| Calendar | `.ics` file import | Simple and realistic |
| Time tracker | CSV import (Toggl-like columns) | Simple and realistic |

**Open questions for the user (not blocking the build):** hackathon length, team size, which LLM provider the team wants to pay for, and whether Slack and email should be live in the final video.

---

## 4. Architecture

```
            ┌──────────────── SOURCES ────────────────┐
            │ Slack (live or demo JSON)                │
            │ Email (live IMAP or demo .eml files)     │
            │ Calendar (.ics)                          │
            │ Time tracker (.csv)                      │
            │ Contract (.pdf) + Goodwill rules (.md)   │
            └──────────────────┬───────────────────────┘
                               ▼
                    1. INGEST (connectors)
          normalise → SourceItem rows in SQLite
                               ▼
                    2. REMEMBER (Cognee)
   cognee.remember(text, dataset_name=<client dataset>,
                   node_set=[<source>, <client slug>])
                               ▼
                    3. EXTRACT (LLM)
     source item → zero or more Requests (structured output)
                               ▼
                    4. MATCH TIME (LLM + rules)
         time entries → the request they belong to
                               ▼
                    5. DECIDE (Cognee recall + LLM + deterministic rules)
     scope check from memory → goodwill rules → money maths
                               ▼
                    6. REMEMBER DECISION (Cognee)
         decision text written back with node_set ["decision"]
                               ▼
                    7. BILL (scheduled job, Stripe test mode)
     1st of the month → Customer → Invoice → Items → finalize → send
                               ▼
                    8. EXPLAIN
     Dashboard "Why?", Ask Tab chat, proof page, disputes,
     health report: all answered from Cognee recall
```

**Processes:**
- `api` (FastAPI): REST API, serves data to the frontend, Stripe webhook endpoint.
- `worker` (asyncio background tasks started inside the FastAPI app on startup):
  - Poll live sources every 30 seconds (only if their env vars are set).
  - Run the processing pipeline (steps 2–6) on new source items.
  - Billing job every 30 seconds: checks the demo clock and raises invoices when a period has closed.
- `web` (Vite dev server): the React app.

**Demo clock:** the app has a "now" that can be overridden (`settings.demo_now`). All period logic uses `get_now()`, never `datetime.now()` directly. This lets the demo move from October to 1 November so the agent raises the invoice on its own.

---

## 5. Repository structure

```
tab/
├── README.md                     # setup + run instructions (written by the agent)
├── PLAN.md                       # this file
├── REPORT.md                     # final report (written by the agent at the end)
├── .env.example
├── Makefile                      # setup, seed, dev, reset, test, acceptance
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py               # FastAPI app, startup tasks
│   │   ├── config.py             # env vars, validation (refuse sk_live_)
│   │   ├── clock.py              # get_now(), demo clock
│   │   ├── db.py                 # SQLModel engine, session
│   │   ├── models.py             # all tables (section 6)
│   │   ├── schemas.py            # API response models
│   │   ├── connectors/
│   │   │   ├── slack_live.py     # Slack Web API poller (optional)
│   │   │   ├── slack_file.py     # demo JSON loader
│   │   │   ├── email_imap.py     # IMAP poller (optional)
│   │   │   ├── email_files.py    # demo .eml loader
│   │   │   ├── calendar_ics.py
│   │   │   ├── timelog_csv.py
│   │   │   └── contract.py       # PDF/MD contract loader
│   │   ├── memory/
│   │   │   ├── cognee_client.py  # thin wrapper: remember, recall, reset, visualize
│   │   │   └── formatting.py     # source item → text record for Cognee
│   │   ├── agent/
│   │   │   ├── llm.py            # structured LLM calls (one place)
│   │   │   ├── extract.py        # step 3
│   │   │   ├── match_time.py     # step 4
│   │   │   ├── terms.py          # contract terms + goodwill rule parsing
│   │   │   ├── decide.py         # step 5
│   │   │   ├── explain.py        # Ask Tab, dispute replies, health report
│   │   │   └── pipeline.py       # orchestrates steps 2–6
│   │   ├── billing/
│   │   │   ├── stripe_client.py
│   │   │   ├── invoicer.py       # step 7
│   │   │   └── webhooks.py       # invoice.paid etc.
│   │   ├── routes/               # one file per area (clients, requests, invoices, proof, ask, memory, settings, demo)
│   │   └── events.py             # agent activity log
│   ├── scripts/
│   │   ├── seed_demo.py          # load demo data end to end
│   │   ├── reset.py              # wipe SQLite + Cognee
│   │   └── acceptance.py         # compare decisions to section 13 expected table
│   └── tests/
├── demo_data/
│   ├── contracts/acme_contract.md + .pdf
│   ├── contracts/bright_bakery_contract.md + .pdf
│   ├── goodwill_rules.md
│   ├── slack/acme-website.json
│   ├── email/*.eml
│   ├── calendar/maya.ics
│   ├── timelog/maya_time_entries.csv
│   └── clients.yaml              # client registry (section 6.1)
└── frontend/
    ├── package.json
    ├── index.html
    └── src/
        ├── main.tsx, App.tsx, api.ts, types.ts
        ├── pages/  Overview, Client, Ask, Memory, Invoice, Proof, Settings
        └── components/ (RequestCard, CategoryBadge, GoodwillMeter, EvidenceList, ActivityFeed, HealthPanel, …)
```

---

## 6. Data model (SQLite via SQLModel)

All money fields are integer pence. All timestamps are timezone-aware UTC, displayed in Europe/London.

### 6.1 Client registry
Clients are set up at onboarding (in the demo, from `demo_data/clients.yaml`). This is how a source item is routed to a client. **Routing is deterministic; it is not guessed by the LLM.** If an item cannot be routed, it is stored with `client_id = null` and shown under "Unassigned" (not billed).

`clients.yaml` for the demo:
```yaml
freelancer:
  name: Maya Chen
  business_name: Maya Chen Design
  email: maya@mayachen.example
clients:
  - slug: acme
    name: Acme Outdoor Ltd
    contact_name: Anna Kowalski
    contact_email: anna@acme-outdoor.example
    email_domains: [acme-outdoor.example]
    slack_channels: [acme-website]
    slack_user_names: [Anna Kowalski]
    calendar_match: ["Acme"]          # event title contains, or attendee domain matches
    timetracker_client: Acme Outdoor
    contract_file: contracts/acme_contract.pdf
  - slug: bright-bakery
    name: Bright Bakery
    contact_name: Tom Reyes
    contact_email: tom@brightbakery.example
    email_domains: [brightbakery.example]
    slack_channels: []
    slack_user_names: []
    calendar_match: ["Bright Bakery"]
    timetracker_client: Bright Bakery
    contract_file: contracts/bright_bakery_contract.pdf
```

### 6.2 Tables

**Client**
`id, slug (unique), name, contact_name, contact_email, email_domains (json), slack_channels (json), slack_user_names (json), calendar_match (json), timetracker_client, cognee_dataset (= "client_<slug>"), stripe_customer_id (nullable), created_at`

**ContractTerm** (extracted from the contract by LLM in step "terms", shown on the dashboard)
`id, client_id, clause_ref (e.g. "2.1"), key, value_json, source_text, confidence`
Required keys per client (if any is missing after extraction → stop and report, do not invent):
- `included_pages` (list of strings)
- `revision_rounds_per_page` (int)
- `bug_fix_window_days` (int) and `delivery_date` (date)
- `meetings_per_month` (int), `meeting_max_minutes` (int)
- `hourly_rate_pence` (int)
- `billing_increment_minutes` (int)
- `invoice_day_of_month` (int), `payment_terms_days` (int)
- `out_of_scope_examples` (list of strings, may be empty)

**GoodwillRule**
`id, client_id (nullable = applies to all), rule_ref (e.g. "G1"), text (plain English, as written by the freelancer), params_json, enabled`
Supported rule types (params_json) for the hackathon:
- `{"type": "small_favour", "max_minutes_exclusive": 20, "max_per_month": 2}`
- `{"type": "always_free_kind", "kind": "typo_fix", "counts_towards_allowance": false}`
If a rule's text cannot be parsed into one of these types, store it with `params_json = null`, show it as "not understood" on the Settings page, and do not apply it.

**SourceItem**
`id, client_id (nullable), source ("slack" | "email" | "calendar" | "timelog" | "contract" | "rules" | "simulated"), external_id (unique per source), occurred_at, author, title (nullable), text, raw_json, period ("2026-10"), cognee_dataset, cognee_node_set (json), remembered_at (nullable), processed_at (nullable)`

**Request**
`id, client_id, source_item_id, requested_at, summary (one line), quote (short verbatim snippet from the source, max 200 chars), kind ("design_change" | "new_deliverable" | "revision" | "bug_fix" | "typo_fix" | "meeting" | "other"), page_or_asset (nullable), revision_round (nullable int), period`

**TimeEntry**
`id, source_item_id, client_id, started_at, minutes, project, description, request_id (nullable), match_confidence (nullable float), match_reason (nullable)`

**Decision**
`id, request_id (unique), category ("included" | "goodwill" | "billable" | "needs_review" | "no_work_logged"), clause_refs (json list), rule_refs (json list), minutes_logged, minutes_billed (after rounding), amount_pence (0 unless billable), value_pence (what it would have cost; set for goodwill and billable), explanation (2–3 plain sentences), evidence (json list of {type, id, label}), cognee_query, cognee_context (text returned by recall, truncated to 4,000 chars), confidence, period, created_at, remembered_at`

**Invoice**
`id, client_id, period, stripe_invoice_id, stripe_customer_id, status ("draft" | "open" | "paid" | "void" | "failed"), total_pence, goodwill_value_pence, hosted_invoice_url, proof_token (random, url-safe, 24+ chars), created_at, error (nullable)`
Unique constraint on `(client_id, period)` so an invoice is never raised twice.

**InvoiceLine**
`id, invoice_id, decision_id, stripe_invoice_item_id, description, amount_pence, is_goodwill`

**Dispute**
`id, invoice_line_id, message, created_at, agent_reply, outcome ("upheld" | "escalated"), evidence (json), cognee_context`

**AgentEvent** (activity feed)
`id, ts, level ("info" | "warn" | "error"), type, message (one human sentence), payload_json`

**Setting**
`key, value` (keys: `demo_now`, `last_slack_ts`, `last_imap_uid`, …)

---

## 7. Cognee: how memory is used (the heart of the product)

Docs to follow (the agent must read these before coding the memory layer, because the API changed in v1.0):
- Python API: https://docs.cognee.ai/python-api
- `remember()`: https://docs.cognee.ai/python-api/remember
- `recall()`: https://docs.cognee.ai/python-api/recall
- Node sets: https://docs.cognee.ai/guides/nodeset-grouping
- Installation and env vars: https://docs.cognee.ai/getting-started/installation
- Agent skills for coding assistants: https://docs.cognee.ai/getting-started/llm-quickstart-skill
- Graph visualization: https://docs.cognee.ai/guides/graph-visualization
- Low-level structured LLM calls: https://docs.cognee.ai/guides/low-level-llm

Facts verified from the docs (15 Oct 2026). If the installed version behaves differently, **report it**:
- Install: `pip install cognee` (Python 3.10–3.14). Default local stores need no servers.
- Env: `LLM_API_KEY` (OpenAI default covers LLM + embeddings). Other providers need both `LLM_*` and `EMBEDDING_*` vars.
- `await cognee.remember(data, dataset_name="...", node_set=[...], self_improvement=...)` stores permanent memory (it runs the add + cognify pipeline).
- `await cognee.recall(query_text, query_type=SearchType.X, datasets=[...], node_name=[...], top_k=..., include_references=True)` returns a list of Pydantic objects; read `result.text`, `result.source`, `result.metadata`. Not dicts.
- `recall()` before any data is ingested raises `RecallPreconditionError`.
- Node-set filtering (`node_name=[...]`) works with graph-completion types and `RAG_COMPLETION`/`CHUNKS`.
- `include_references=True` adds an `Evidence:` block; structured `metadata.evidence` is filled for `RAG_COMPLETION` and `GRAPH_COMPLETION`, not for `HYBRID_COMPLETION`.
- `await cognee.forget(everything=True)` wipes all memory (used by `make reset`).

### 7.1 Layout
- **One dataset per client:** `client_acme`, `client_bright-bakery`. Keeps clients isolated.
- **Node sets tag the source:** `["contract", <slug>]`, `["goodwill_rules", <slug>]`, `["slack", <slug>]`, `["email", <slug>]`, `["calendar", <slug>]`, `["timelog", <slug>]`, `["decision", <slug>]`, `["dispute", <slug>]`.
- Goodwill rules that apply to all clients are remembered into **each** client dataset.

### 7.2 What text goes into Cognee
Every source item is converted to a short, self-describing text record so the graph has the facts needed for later answers. Format (exact):
```
[SOURCE ITEM {source}:{external_id}]
Client: {client name}
Date: {YYYY-MM-DD HH:MM Europe/London}
From: {author}
Channel: {slack channel | email subject | calendar title | time tracker project}
Text: {text}
```
Decisions are written back as:
```
[DECISION decision:{id}]
Client: {client name}
Request: {summary} (requested {date} via {source}:{external_id})
Verdict: {category}
Clauses: {clause_refs} | Goodwill rules: {rule_refs}
Time logged: {minutes} min, billed {minutes_billed} min, amount £{x.xx}, value £{y.yy}
Reason: {explanation}
```

### 7.3 When Cognee is called
| Step | Call | Purpose |
|---|---|---|
| Seed / ingest | `remember(records, dataset_name=client dataset, node_set=[source, slug])` batched per client per source | Build memory. Batch to keep LLM cost and time down |
| Contract terms | `recall("List every numbered clause...", query_type=RAG_COMPLETION, datasets=[client], node_name=["contract"], include_references=True)` plus the contract text itself | Extract `ContractTerm` rows with clause refs |
| Revision history | `recall("How many revision rounds has {page} had before {date}? List each with date.", query_type=GRAPH_COMPLETION, datasets=[client], include_references=True)` | Count revision rounds from memory, including September history |
| Scope check | `recall("Is this covered by the contract: '{summary}'? Quote the clause numbers.", query_type=GRAPH_COMPLETION, datasets=[client], node_name=["contract"], include_references=True)` | Ground the scope decision in the contract |
| Decision write-back | `remember(decision record, node_set=["decision", slug])` batched after each pipeline run | So every "why?" is answerable from memory |
| Ask Tab / Why? | `recall(question, query_type=GRAPH_COMPLETION, datasets=[client or all], include_references=True)` | Explanations from memory |
| Disputes | `recall("Evidence for invoice line '{desc}' and the dispute '{msg}'", ...)` | Answer disputes from memory |
| Health report | `recall("Summarise how often {client} asked for work outside the contract this month and what kind", ...)` | Narrative paragraph |
| Memory page | Cognee graph visualization to HTML | Show the graph in the dashboard |

**Rule:** every recall query and the returned context are saved (on the Decision, Dispute, or an AgentEvent) so the UI can show "what Tab remembered".

**Speed:** use `self_improvement=False` on `remember()` during seeding unless the agent measures that it is fast enough with it on. Report the choice and the seeding time.

---

## 8. Decision logic (step 3 to 5)

### 8.1 Step 3: extract requests (LLM, structured output)
Input: one source item (with client name and date). Output JSON:
```json
{ "requests": [ { "summary": "...", "quote": "...", "kind": "revision", "page_or_asset": "Home", "is_future_work": false } ] }
```
- Messages that are thanks, FYI or chit-chat → `requests: []`.
- Calendar events are always one request of kind `meeting` (no LLM needed).
- Time entries are never requests.

### 8.2 Step 4: match time entries to requests
For each time entry with a client:
1. Candidates = requests of the same client within −1 to +3 days of the entry date.
2. If one candidate → LLM confirms match (yes/no + confidence).
3. If several → LLM picks one or none, with a reason and confidence.
4. Confidence < 0.7 → leave unmatched, AgentEvent `warn`.
Calendar meetings use the event duration as minutes (no time entry needed).

### 8.3 Step 5: decide (order matters)
For each request in the period:

1. **No time:** no matched time entry and not a meeting → `no_work_logged` (not billed, shown in the feed).
2. **Meeting:** deterministic. Count the client's meetings in the calendar month in date order. Meeting number ≤ `meetings_per_month` and duration ≤ `meeting_max_minutes` → `included` (clause 4.1). Otherwise `billable` (clause 4.2): whole meeting if over the count, only the extra minutes if over the length.
3. **Scope check (Cognee + LLM):** call recall (section 7.3 "scope check", and "revision history" when kind is `revision`), then an LLM call with the request, the contract terms and the recalled context. Output:
   ```json
   { "in_scope": true, "clause_refs": ["3.2"], "revision_round": 2, "is_typo_fix": false, "reasoning": "...", "confidence": 0.0-1.0 }
   ```
   - `confidence < 0.7` → `needs_review` (not billed). Never guess.
   - `in_scope = true` → `included`.
4. **Goodwill (deterministic, only for out-of-scope requests):**
   - If `is_typo_fix` and an `always_free_kind: typo_fix` rule applies to the client → `goodwill`, does **not** use the allowance.
   - Else if `minutes_logged < max_minutes_exclusive` and favours already used this month (goodwill decisions that count towards the allowance, by request date) `< max_per_month` → `goodwill`.
5. **Otherwise** → `billable`.

**Money maths (deterministic, never by the LLM):**
- `minutes_billed = ceil(minutes_logged / billing_increment_minutes) * billing_increment_minutes`
- `value_pence = minutes_billed * hourly_rate_pence / 60` (integer; the rate and increment make this exact in the demo)
- `amount_pence = value_pence` if billable, else 0.
- Included items: `value_pence = 0`, `amount_pence = 0`.

**Explanation:** 2–3 plain sentences, written by the LLM from the decision fields only (no new facts), for example: *"Billable. The contract covers five pages (clause 2.1) and Careers isn't one of them. Anna asked for it by email on 22 Oct and 4h was logged, so it's billed at £50/h (clause 5.2)."*

**Evidence list** on each decision: the source item(s) of the request, the matched time entry, the contract clause(s), the goodwill rule (if any).

---

## 9. Stripe (test mode only)

Docs: https://docs.stripe.com/api/invoiceitems, https://docs.stripe.com/api/invoices, https://docs.stripe.com/api/invoice-line_item

**Safety:** on startup, if `STRIPE_SECRET_KEY` does not start with `sk_test_`, refuse to start with a clear error.

### 9.1 Billing job (no human raises the bill)
Runs every 30 seconds. For each client and each period `P` where:
- `get_now()` ≥ the `invoice_day_of_month` of the month after `P` (contract clause 5.4: the 1st), and
- no Invoice row exists for `(client, P)`,

then:
1. Collect decisions for `P`: `billable` and `goodwill`. Ignore `needs_review` and `no_work_logged`, and log a `warn` AgentEvent if any `needs_review` exist ("2 items held back for review").
2. If there are no billable decisions → do **not** create a Stripe invoice. Log an info event ("Nothing to bill for Bright Bakery in October. 1 favour given.").
3. Ensure a Stripe Customer exists (`stripe.Customer.create(name, email, metadata={"tab_client_id": ...})`), save the id.
4. Create a draft invoice: `stripe.Invoice.create(customer=..., collection_method="send_invoice", days_until_due=<payment_terms_days>, currency="gbp", description="Extra work for October 2026. See the evidence for every line: {PUBLIC_BASE_URL}/proof/{proof_token}", metadata={"tab_invoice_id": ..., "period": "2026-10"})`. Also try to add the proof link as a custom field (name "Proof of work"); if Stripe rejects it (length limits), skip it and report.
5. For each decision, create an invoice item attached to that draft invoice: `stripe.InvoiceItem.create(customer=..., invoice=<invoice id>, currency="gbp", amount=<amount_pence>, description=..., metadata={"tab_decision_id": ...})`.
   - Billable line description: `"{summary} ({date}, {minutes_billed} min @ £50/h, clause {refs})"`.
   - Goodwill line description: `"On the house: {summary} ({date}, worth £{value})"` with `amount=0`.
   - **If Stripe rejects a zero amount**, do not invent a workaround silently: list goodwill items in the invoice `footer` instead, keep them on the proof page, and report it.
6. Finalize: `stripe.Invoice.finalize_invoice(id)`. Save `hosted_invoice_url`.
7. Send: `stripe.Invoice.send_invoice(id)` (in test mode Stripe may not email real addresses; that's fine).
8. Save Invoice + InvoiceLine rows, `remember()` a short invoice record into Cognee (`node_set=["invoice", slug]`), and log an AgentEvent ("Raised invoice for Acme: £487.50, 5 billable lines, 3 favours").
9. Any Stripe error → Invoice row with `status="failed"` and `error`, AgentEvent `error`, and **no retry loop that could double-bill** (the unique constraint protects this).

Verify every Stripe parameter name against the current docs before using it. If a documented parameter fails, report the exact error.

### 9.2 Payment in the demo
Open `hosted_invoice_url`, pay with Stripe's test card `4242 4242 4242 4242` (any future date, any CVC). Status updates through:
- **Webhook (preferred):** `POST /api/stripe/webhook`, verifies `STRIPE_WEBHOOK_SECRET`, handles `invoice.paid`, `invoice.payment_failed`, `invoice.voided`. Local forwarding: `stripe listen --forward-to localhost:8000/api/stripe/webhook`.
- **Fallback:** if no webhook secret is set, poll open invoices every 60 seconds with `stripe.Invoice.retrieve`.

---

## 10. User interface

**Look and feel:** calm, trustworthy, finance-grade. White background, one accent colour (deep green), clear typography (Inter from Google Fonts), generous spacing. Dark mode is optional (skip if short on time).

**Category colours (used everywhere):**
- Included → slate grey, label "Included"
- Goodwill → green, label "On the house"
- Billable → amber, label "Billable"
- Needs review → red, label "Needs review"
- No work logged → light grey, label "No time logged"

### 10.1 Pages

**Overview (`/`)**
- Four stat cards for the current period: *Recovered* (sum of billable), *On the house* (count + value of goodwill), *Needs review* (count), *Invoices raised* (count + paid).
- Client cards: name, period tab total, favours used ("2 of 2"), health badge (Healthy / Watch / Over scope), link to the client page.
- Live activity feed (AgentEvents, newest first, polls every 3 seconds).

**Client (`/clients/:slug`)**
- Header: client name, contact, contract summary chips built from ContractTerm rows (each chip shows the clause ref, for example "5 pages · 2.1", "2 revisions/page · 3.2", "£50/h · 5.2").
- Goodwill meter: favours used this month vs allowance, plus a line for typo-rule favours ("+1 typo fix, always free").
- Period selector (September, October).
- Request timeline: one card per request, newest first. Each card: source icon (Slack, email, calendar), date, the short quote, category badge, clause chips, minutes logged, amount or value, and a "Why?" toggle that shows the explanation, the evidence list (clicking an item opens the raw source item in a side panel) and "What Tab remembered" (the stored Cognee query and context, collapsed by default).
- Invoices for this client (status, total, link to Stripe hosted invoice, link to proof page).
- Health panel (section 10.2).

**Ask Tab (`/ask`)**
- Chat box. Client selector (All clients or one). Example prompts as chips: "Why did you bill Acme £200?", "Which favours did Acme get in October?", "How many revision rounds has the Acme Home page had?"
- Answers come from Cognee recall (section 7.3). Show the references under the answer.

**Memory (`/memory`)**
- Embedded Cognee graph visualization (HTML generated by the backend, served from `/api/memory/graph.html`, refreshed with a button).
- Counts per node set per client (contract, slack, email, calendar, timelog, decision, invoice, dispute).

**Invoice (`/invoices/:id`)** (internal view)
- Stripe ids, status, lines with links to their decisions, disputes and agent replies.

**Proof page (`/proof/:token`)** (the client's view, no navigation chrome)
- Header: "Maya Chen Design · Invoice for October 2026 · £487.50 · Status".
- Button: "Pay invoice" → Stripe hosted invoice URL.
- Section "Extra work" (billable lines): each line shows the description, amount, and an expandable evidence block: the client's own message (quote, date, channel), the hours logged, and the contract clause text.
- Section "On the house" (goodwill lines): each with the value and a short thank-you note ("Included free as a favour, no charge").
- Each billable line has "Question this line". The client types a message → the agent replies on the page within a few seconds (section 10.3).

**Settings (`/settings`)**
- Integrations: Slack (Live / Demo file / Off), Email (Live IMAP / Demo files / Off), Calendar (file), Time tracker (file), Stripe (Test mode connected + account id). Show **honest status**: never show "Live" unless the connector actually succeeded in the last poll.
- Goodwill rules: plain-English text per rule, the parsed parameters, and a "not understood" warning where parsing failed. Editing a rule re-parses it and re-runs decisions for the current open period.
- Demo controls (clearly labelled "Demo controls"): set the demo clock (date-time picker + "Jump to 1 Nov 09:00"), "Simulate a client message" (choose client and channel, type text; stored with `source="simulated"` and shown with a "Simulated" tag everywhere), "Reset demo" (runs reset + seed).

### 10.2 Health report (per client, per period)
Deterministic numbers:
- `hours_total` = all matched client minutes in the period / 60
- `hours_in_scope` = included minutes / 60
- `hours_beyond_scope` = (billable + goodwill minutes) / 60
- `beyond_scope_share` = hours_beyond_scope / hours_total
- favours used, amount billed, items needing review
Badge: < 20% → Healthy, 20–50% → Watch, > 50% → Over scope.
Narrative: one paragraph from the LLM using these numbers plus a Cognee recall of the period's requests. Must not contain any number that isn't in the deterministic set.

### 10.3 Disputes
When a client questions a line:
1. Save the Dispute, `remember()` it (`node_set=["dispute", slug]`).
2. Recall evidence for that line (section 7.3).
3. LLM drafts a polite reply that cites the clause, the client's own message (date + quote) and the hours.
4. Outcome rules:
   - The decision has a clause ref **and** a client source item **and** a matched time entry, and the dispute raises no fact that is absent from memory → `upheld`, reply shown on the proof page.
   - Otherwise → `escalated`: the client sees "Maya will get back to you personally", and the freelancer sees it highlighted in the dashboard.
   - The agent never cancels or credits a charge by itself.

---

## 11. Demo data (exact)

The agent creates these files exactly as specified. Names and emails use `.example` domains (fictional). Times are Europe/London.

### 11.1 Acme contract (`acme_contract.md`, also rendered to PDF)
**Website Design Services Agreement** between **Maya Chen Design** (the Designer) and **Acme Outdoor Ltd** (the Client). Signed 1 September 2026.

1. **Parties and timeline**
   - 1.1 The Designer will deliver the website by 30 September 2026 (the Delivery Date).
2. **Scope**
   - 2.1 The Designer will design five (5) pages: Home, About, Services, Portfolio, Contact.
   - 2.2 Each page includes a desktop and a mobile layout.
   - 2.3 Bug fixes on delivered pages are included for 30 days after the Delivery Date.
   - 2.4 Anything not listed in 2.1 to 2.3, including additional pages, print materials and social media assets, is out of scope and billed under clause 5.
3. **Revisions**
   - 3.1 The Client sends feedback by email or in the shared Slack channel.
   - 3.2 Up to two (2) revision rounds per page are included.
   - 3.3 Additional revision rounds are billed under clause 5.
4. **Meetings**
   - 4.1 Up to two (2) meetings per calendar month, each up to 60 minutes, are included.
   - 4.2 Additional meetings, and time beyond 60 minutes in any meeting, are billed under clause 5.
5. **Fees and invoicing**
   - 5.1 The fixed fee for the scope in clause 2 is £4,000 (paid separately, not handled by Tab).
   - 5.2 Out-of-scope work is charged at £50 per hour.
   - 5.3 Time is billed in 15-minute increments, rounded up per task.
   - 5.4 Out-of-scope work is invoiced on the 1st of each month for the previous month. Payment is due within 14 days.

### 11.2 Bright Bakery contract
Same structure. Scope: menu design (A4, 2 pages) and window signage (1 poster). Delivery date 15 September 2026. 2 revision rounds per deliverable. **One (1)** meeting per month up to 30 minutes. £50/h, 15-minute increments, invoiced on the 1st, 14 days.

### 11.3 Goodwill rules (`goodwill_rules.md`)
- **G1 (all clients):** "Small favours that take under 20 minutes are free, up to 2 per client per calendar month. After that, they're billed normally."
- **G2 (Acme only):** "Typo fixes for Acme are always free and don't count towards the favour allowance."

### 11.4 Acme source items

History (September, for memory only, never billed in October):
| ID | Source | Date | Text (summary; write as a natural message) |
|---|---|---|---|
| S01 | email | 15 Sep 2026 | Anna: round 1 feedback on the Home page (bigger hero, warmer colours) |
| S02 | email | 18 Sep 2026 | Anna: round 1 feedback on the About page |
| S03 | timelog | 15 Sep 2026 | 120 min, "Acme – Home page revisions round 1" |

October (the demo period):
| ID | Source | Date | Message (summary; write naturally) | Time entry |
|---|---|---|---|---|
| A02 | email | 3 Oct 09:40 | Anna: "Home page round 2 feedback": headline copy and button colour | 120 min "Acme – Home page revisions round 2" (3 Oct) |
| A03 | slack | 6 Oct 14:05 | Anna: "Sorry, could we do one more pass on the Home hero? The team wants the headline bigger and a different photo." | 90 min "Acme – Home hero tweaks" (6 Oct) |
| A04 | slack | 8 Oct 11:20 | Anna: "Could you swap the footer logo for the new PNG I put in the shared folder?" | 15 min "Acme – footer logo swap" (8 Oct) |
| N01 | slack | 9 Oct 08:55 | Anna: "Thanks, the logo looks perfect!" | none |
| A05 | email | 10 Oct 10:15 | Anna: "We have a launch event on 30 Oct. Could you design a printable A4 flyer to match the new site?" | 180 min "Acme – A4 launch flyer" (10 Oct) |
| A06 | calendar | 13 Oct 10:00–11:00 | "Acme weekly sync" (attendee anna@acme-outdoor.example) | event duration |
| N02 | email | 14 Oct 16:30 | Anna: "FYI, our CEO loved the new design!" | none |
| A07 | slack | 16 Oct 13:10 | Anna: "Can you resize the hero image to 1080×1080 for Instagram? Just need it today." | 15 min "Acme – Instagram hero resize" (16 Oct) |
| N03 | timelog | 19 Oct | 60 min, project "Portfolio site update", no client | (not a client entry, must be ignored) |
| A08 | calendar | 20 Oct 10:00–11:00 | "Acme weekly sync" | event duration |
| A09 | slack | 21 Oct 15:45 | Anna: "Quick one, could you export all the icons as SVGs for the dev team?" | 15 min "Acme – icon SVG export" (21 Oct) |
| A10 | email | 22 Oct 09:05 | Anna: "We've decided we need a Careers page too, same style as Services. Can you add it?" | 240 min "Acme – Careers page design" (22–23 Oct, one entry) |
| A11 | slack | 24 Oct 17:20 | Anna: "The contact form looks broken on my phone, can you check?" | 30 min "Acme – contact form mobile fix" (24 Oct) |
| A12 | calendar | 27 Oct 10:00–11:00 | "Acme weekly sync" | event duration |
| A13 | slack | 29 Oct 12:00 | Anna: "Spotted a typo on the flyer: 'Lauch' should be 'Launch'. Can you fix it before printing?" | 10 min "Acme – flyer typo fix" (29 Oct) |
| A14 | slack | 30 Oct 16:00 | Anna: "Next month, could you also redesign our pitch deck?" | none |

### 11.5 Bright Bakery source items (all email or calendar, October)
| ID | Source | Date | Message | Time entry |
|---|---|---|---|---|
| B01 | email | 5 Oct | Tom: round 1 revision notes on the menu | 60 min "Bright Bakery – menu revisions round 1" |
| B02 | calendar | 12 Oct 10:00–10:30 | "Bright Bakery check-in" | event duration |
| B03 | email | 19 Oct | Tom: "Could you change the croissant price from £2.80 to £3.00?" | 10 min "Bright Bakery – croissant price update" |
| B04 | email | 26 Oct | Tom: round 2 (final) revision notes on the menu | 60 min "Bright Bakery – menu revisions round 2" |

Note: B03 is a content update on the delivered menu, not a revision round. It must not be counted as revision round 2. B04's message says explicitly that it is the second round.

### 11.6 File formats
- **Slack demo file** (`slack/acme-website.json`): list of `{ "ts": "<unix seconds as string>", "user": "U_ANNA", "user_name": "Anna Kowalski", "channel": "acme-website", "text": "..." }`.
- **Email** (`email/*.eml`): RFC 822 files with From, To (maya@mayachen.example), Subject, Date, Message-ID, plain-text body.
- **Calendar** (`calendar/maya.ics`): one VEVENT per meeting with UID, SUMMARY, DTSTART, DTEND (TZID Europe/London), ATTENDEE.
- **Time log** (`timelog/maya_time_entries.csv`): columns `date,start_time,duration_minutes,client,project,description`. Client values must match `timetracker_client` in `clients.yaml`, empty for N03.

---

## 12. Build phases

Work in this order. Each phase ends with its checks passing before the next starts. If time runs out, the later phases are the ones to drop, and the report must say so.

**Phase 0: Setup**
- Repo structure, `.env.example`, Makefile, README skeleton.
- Read the Cognee docs listed in section 7 and the Stripe docs in section 9. Install Cognee's agent skills if the coding tool supports them.
- Smoke tests: (a) `cognee.remember` + `cognee.recall` round trip on one sentence; (b) Stripe test key creates and deletes a test Customer.
- ✅ Check: both smoke tests pass and are recorded in the report with versions (cognee version, stripe library version, Python version).

**Phase 1: Demo data + ingestion**
- Create every file in section 11 exactly.
- Connectors for files (Slack JSON, .eml, .ics, CSV, contract PDF/MD).
- Client routing from `clients.yaml`.
- `remember()` into per-client datasets with node sets (section 7).
- ✅ Check: SourceItem counts match section 11:
  - Acme: 1 contract; September: 2 emails + 1 time entry; October: 8 Slack messages, 4 emails, 3 calendar events, 9 time entries.
  - Bright Bakery: 1 contract; October: 3 emails, 1 calendar event, 3 time entries.
  - 1 unassigned time entry (N03).
  - Goodwill rules remembered into both client datasets.
  - Recall "What did Anna ask for on 22 October?" mentions the Careers page.

**Phase 2: Terms and rules**
- Contract terms extraction with clause refs; goodwill rule parsing.
- ✅ Check: all required ContractTerm keys exist for both clients with the values in section 11; G1 and G2 parsed correctly.

**Phase 3: The brain**
- Request extraction, time matching, decisions, explanations, decision write-back to Cognee.
- ✅ Check: `make acceptance` (section 13) passes. Report the accuracy and every mismatch.

**Phase 4: Stripe billing**
- Billing job, demo clock, Customer, Invoice, Items, finalize, send, webhook or polling.
- ✅ Check: jumping the clock to 2026-11-01 09:00 creates exactly one Acme invoice of **£487.50** in Stripe test mode with 5 billable lines and 3 goodwill lines, and no Bright Bakery invoice. Running the job again creates nothing new. Paying the invoice marks it paid in Tab (for an automated check, pay it through the API with a Stripe test payment method after confirming the exact parameters in the docs; the demo video pays it by hand on the hosted page with card 4242 4242 4242 4242).

**Phase 5: Dashboard**
- Overview, Client, Ask Tab, Memory, Invoice, Settings pages (section 10).
- ✅ Check: every number on screen matches the database; "Why?" works on every card.

**Phase 6: Proof page + disputes**
- ✅ Check: the proof link in the Stripe invoice opens the page; disputing the Careers line returns an `upheld` reply citing clause 2.1 and Anna's 22 Oct email; a dispute that says "Maya told me on the phone it was free" is `escalated`.

**Phase 7: Health report**
- ✅ Check: Acme numbers match section 13.3; badge "Over scope". Bright Bakery badge "Healthy".

**Phase 8: Live sources (optional)**
- Slack live poller (bot token, `conversations.history`), IMAP poller.
- ✅ Check: a message posted in the real Slack channel appears in the dashboard within 60 seconds and is decided. If credentials aren't provided, skip and report "not tested".

**Phase 9: Polish + demo readiness**
- `make reset && make seed` produces the full demo state from scratch; record the time it takes.
- README with setup, env vars, run commands, the demo script (section 14.2).

---

## 13. Acceptance tests (expected results)

`backend/scripts/acceptance.py` loads the demo, runs the pipeline, and compares against this table. It prints a pass/fail line per item and a summary. **Do not change this table to make tests pass.** If the agent believes an expected value is wrong, report it.

### 13.1 Acme, October 2026
| ID | Expected category | Clause / rule | Minutes logged | Minutes billed | Amount | Value |
|---|---|---|---|---|---|---|
| A02 | included | 3.2 (round 2) | 120 | 0 | £0.00 | £0.00 |
| A03 | billable | 3.3 (round 3) | 90 | 90 | £75.00 | £75.00 |
| A04 | goodwill | G1 (favour 1 of 2) | 15 | 15 | £0.00 | £12.50 |
| A05 | billable | 2.4 (print material) | 180 | 180 | £150.00 | £150.00 |
| A06 | included | 4.1 (meeting 1 of 2) | 60 | 0 | £0.00 | £0.00 |
| A07 | goodwill | G1 (favour 2 of 2) | 15 | 15 | £0.00 | £12.50 |
| A08 | included | 4.1 (meeting 2 of 2) | 60 | 0 | £0.00 | £0.00 |
| A09 | billable | 2.4 + G1 allowance used | 15 | 15 | £12.50 | £12.50 |
| A10 | billable | 2.1 / 2.4 (extra page) | 240 | 240 | £200.00 | £200.00 |
| A11 | included | 2.3 (bug fix within 30 days) | 30 | 0 | £0.00 | £0.00 |
| A12 | billable | 4.2 (third meeting) | 60 | 60 | £50.00 | £50.00 |
| A13 | goodwill | G2 (typo, no allowance used) | 10 | 15 | £0.00 | £12.50 |
| A14 | no_work_logged | none | 0 | 0 | £0.00 | £0.00 |
| N01, N02 | not requests | | | | | |
| N03 | unassigned, ignored | | | | | |

**Acme totals:** billable **£487.50** (5 lines), goodwill value **£37.50** (3 lines).

### 13.2 Bright Bakery, October 2026
| ID | Expected category | Clause / rule | Minutes | Amount | Value |
|---|---|---|---|---|---|
| B01 | included | revisions round 1 | 60 | £0.00 | £0.00 |
| B02 | included | meeting 1 of 1 | 30 | £0.00 | £0.00 |
| B03 | goodwill | G1 (favour 1 of 2) | 10 | £0.00 | £12.50 |
| B04 | included | revisions round 2 | 60 | £0.00 | £0.00 |

**Bright Bakery:** nothing billable → no Stripe invoice.

### 13.3 Health report numbers (Acme, October)
- Hours total: 120+90+15+180+60+15+60+15+240+30+60+10 = 895 min = **14.92 h**
- In scope: 120+60+60+30 = 270 min = **4.50 h**
- Beyond scope (billable + goodwill, actual minutes): 90+15+180+15+15+240+60+10 = 625 min = **10.42 h**
- Beyond-scope share: 625 / 895 = **69.8%** → badge **Over scope**
- Bright Bakery: 10 / 160 min = **6.3%** → **Healthy**

---

## 14. Running it

### 14.1 Environment variables (`.env.example`)
```
# LLM (used by Cognee and by Tab)
LLM_API_KEY=
# LLM_PROVIDER=        # optional, Cognee default is OpenAI
# LLM_MODEL=           # optional
# EMBEDDING_PROVIDER=  # required if LLM_PROVIDER is not OpenAI
# EMBEDDING_MODEL=
# EMBEDDING_API_KEY=

# Stripe (test mode only, must start with sk_test_)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=     # optional, enables webhooks; otherwise polling

# App
PUBLIC_BASE_URL=http://localhost:5173
DATABASE_URL=sqlite:///./tab.db
DEMO_MODE=true

# Optional live sources
SLACK_BOT_TOKEN=
SLACK_CHANNEL_IDS=
IMAP_HOST=
IMAP_USER=
IMAP_PASSWORD=
```

### 14.2 Commands
- `make setup`: create the Python venv, install backend + frontend dependencies.
- `make reset`: wipe SQLite and Cognee memory (`cognee.forget(everything=True)`).
- `make seed`: load demo data and run the pipeline (demo clock set to 2026-10-31 18:00).
- `make dev`: run API (port 8000) and web (port 5173).
- `make test`: unit tests (money maths, rounding, meeting counting, goodwill allowance, routing).
- `make acceptance`: section 13.

### 14.3 Demo video script (about 2 minutes)
1. **Problem (15s):** "Three small favours a week is 4+ hours of unpaid work a month."
2. **Meet Maya (10s):** Overview page, two clients.
3. **The month (30s):** Acme client page: scroll the timeline, show one included item, one favour, one billable item; open "Why?" on the Careers page card and show the evidence and "What Tab remembered".
4. **Live trigger (15s):** simulate (or post in real Slack) a new request, watch it appear and get decided.
5. **No human raises the bill (20s):** jump the clock to 1 Nov. The activity feed shows "Raised invoice for Acme: £487.50". Open it in Stripe test mode, with the £0 "On the house" lines.
6. **Proof + dispute (20s):** open the proof page, dispute the Careers line, show the upheld reply. Pay with the test card.
7. **Memory (10s):** Memory page graph, then Ask Tab: "Why did you bill Acme £200?"
8. **Close (10s):** health report "Acme: 70% beyond scope, consider raising the rate."

---

## 15. Rules for the coding agent

1. **Do not hallucinate.** If an API, parameter, import path or behaviour isn't confirmed by the docs or by running it, test it first. If it fails, report the exact error instead of inventing a workaround.
2. **Do not assume.** If something in this plan is unclear, contradictory or impossible, write it down in the report under "Unclear / needs decision", choose the most conservative option that doesn't change the product, and say exactly what you chose.
3. **Never fake results.** No hardcoded decisions, amounts or LLM outputs in the app code (the acceptance table is only used by `acceptance.py`). Never mark a connector "Live" if it didn't connect. Simulated data is always labelled "Simulated".
4. **Money safety.** Test mode only. Integer pence. Never create a second invoice for the same client and period. Never auto-credit or refund.
5. **Secrets.** Never commit `.env`. Never print keys in logs.
6. **Verify, then claim.** Something is "done" only when its phase check passed. Partial work is reported as partial.
7. **Keep going when possible.** If a phase is blocked, record the blocker, then continue with any later phase that doesn't depend on it.

---

## 16. Final report format (`REPORT.md`)

The agent writes this at the end, and the user pastes it back to the planning conversation.

```
# Tab: Build Report

## 1. Summary
- Overall status: (complete / partial / blocked)
- What works end to end, in 3–5 bullets
- Time spent per phase (approx.)

## 2. Environment
- OS, Python, Node, cognee version, stripe library version, LLM provider + model used

## 3. Phase checklist
| Phase | Status (done / partial / not started / blocked) | Check result | Notes |

## 4. Acceptance results
- Pasted output of `make acceptance`
- Accuracy: X / 16 Acme checks (13 decisions + N01, N02, N03), Y / 4 Bright Bakery decisions
- Every mismatch: ID, expected, got, likely reason

## 5. Stripe results
- Invoice id(s), total, number of lines, whether £0 lines were accepted
- Webhook or polling, and whether payment status updated

## 6. Cognee usage
- Datasets and node sets created, seeding time, self_improvement setting
- Any API differences from PLAN.md section 7

## 7. Deviations from the plan
- What changed, why, and the impact

## 8. Unclear / needs decision
- Each question, the option chosen for now, and the alternative

## 9. Blockers and errors
- Exact error messages and what was tried

## 10. Not done / pending
- Prioritised list of what's left

## 11. How to run the demo
- Exact commands from a clean clone, and known issues
```
