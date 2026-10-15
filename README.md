# Tab

Tab keeps a fair tab with every client. It reads where a freelancer's work happens (Slack, email, calendar,
time tracker, the contract), remembers everything per client in [Cognee](https://docs.cognee.ai), decides
for every client request whether it is **included**, **a favour on the house** or **billable**, and on the
1st of the month raises the Stripe invoice itself (test mode), with a proof page for every line.

`PLAN.md` is the specification. `REPORT.md` is the build report: what works, what is pending and why.

## Requirements

- macOS or Linux, [uv](https://docs.astral.sh/uv/) (installs Python 3.12), Node 20+ and npm
- An OpenAI API key (`LLM_API_KEY`), used by Cognee and by Tab for LLM calls and embeddings
- A Stripe **test mode** secret key (`STRIPE_SECRET_KEY=sk_test_...`). Tab refuses to start with any other kind of key.

## Setup

```bash
cp .env.example .env        # then fill in LLM_API_KEY and STRIPE_SECRET_KEY
make setup                  # Python 3.12 venv (uv) + backend and frontend dependencies
```

### Environment variables

| Variable | Required | What it does |
|---|---|---|
| `LLM_API_KEY` | yes | OpenAI key for Cognee (graph building, embeddings, recall) and Tab's structured LLM calls |
| `LLM_PROVIDER`, `LLM_MODEL`, `EMBEDDING_*` | no | Use another provider (set both LLM and embedding variables, see the Cognee install docs) |
| `STRIPE_SECRET_KEY` | for billing | Must start with `sk_test_`. Empty: the app runs and billing is disabled. Any other key: the app refuses to start |
| `STRIPE_WEBHOOK_SECRET` | no | Enables `POST /api/stripe/webhook`. Without it Tab polls open invoices every 60 seconds |
| `PUBLIC_BASE_URL` | no | Base of the proof links put on Stripe invoices (default `http://localhost:5173`) |
| `DATABASE_URL` | no | Default `sqlite:///./tab.db` (relative to `backend/`) |
| `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_IDS` | no | Live Slack polling (`conversations.history`) |
| `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD` | no | Live email polling over IMAP |

Tab also sets these Cognee defaults (override them in `.env` if needed): local stores in `backend/.cognee/`,
`TELEMETRY_DISABLED=1`, `AUTO_FEEDBACK=false`, `SKILL_GATE_ENABLED=false`, and `remember(self_improvement=False)`
(`TAB_COGNEE_SELF_IMPROVEMENT=true` turns self-improvement on).

**Without keys** the app still starts: demo files load, and every page says plainly "LLM key missing" or
"Stripe key missing" instead of showing made-up data. Placeholder values such as `sk-xxx` count as missing.

## Commands

| Command | What it does |
|---|---|
| `make setup` | Install everything |
| `make reset` | Wipe SQLite and Cognee memory (`cognee.forget(everything=True)`) |
| `make seed` | Load the demo data, remember it in Cognee, extract terms and requests, match time, decide. Sets the demo clock to 31 Oct 2026 18:00 |
| `make dev` | API on http://localhost:8000, web app on http://localhost:5173 |
| `make test` | Unit tests (money maths, rounding, meetings, goodwill allowance, routing, clock, duplicate-invoice guard, ...). No keys needed |
| `make acceptance` | Compares the pipeline's decisions with `PLAN.md` section 13 |
| `make smoke` | Phase 0 smoke tests: Cognee remember/recall round trip, Stripe test Customer create + delete |
| `make phase1`, `make phase2`, `make phase6` | Phase checks that need keys (memory, contract terms, proof link + disputes) |
| `make billing-check` / `make pay-check` | Phase 4: jump to 1 Nov 09:00, verify the Stripe invoice; `pay-check` also pays it with the test card through the API |

From a clean clone: `make setup && make reset && make seed && make dev`.

## How it works

```
sources (Slack JSON, .eml, .ics, CSV, contract PDF, goodwill_rules.md)
  -> ingest: SourceItem rows, routed to a client deterministically from demo_data/clients.yaml
  -> remember: cognee.remember(records, dataset_name="client_<slug>", node_set=[source, slug])
  -> terms: contract terms with clause refs (recall + LLM, validated); goodwill rules parsed and validated
  -> extract: requests from each message (LLM); calendar events become meeting requests (no LLM)
  -> match: time entries to requests (LLM, confidence >= 0.7, otherwise left unmatched)
  -> decide: meetings counted deterministically; scope check from Cognee recall + LLM;
             goodwill rules and money maths deterministic (integer pence, 15-minute rounding)
  -> remember decisions back into Cognee (node_set ["decision", slug])
  -> bill: every 30 s the billing job checks the demo clock; on the invoice day it creates the
           Stripe Customer, draft Invoice, Invoice Items (including £0 "On the house" lines),
           finalizes and sends. The Invoice row is written first (unique per client and period),
           so an invoice can never be raised twice.
  -> explain: "Why?" on every decision, Ask Tab, the proof page, disputes, the health report
```

Code map: `backend/app/connectors` (sources), `backend/app/memory` (Cognee), `backend/app/agent`
(extract, match, terms, decide, explain, pipeline), `backend/app/billing` (Stripe), `backend/app/routes`
(API), `frontend/src/pages` (UI).

## Demo script (about 2 minutes)

Before recording: `make reset && make seed && make dev`, open http://localhost:5173.

1. **Problem (15 s):** "Three small favours a week is 4+ hours of unpaid work a month."
2. **Meet Maya (10 s):** Overview page, two clients.
3. **The month (30 s):** Acme client page. Scroll the timeline: an included item (Home page round 2), a favour
   (footer logo swap), a billable item. Open **Why?** on the Careers page card: explanation, evidence (click the
   email to see it raw) and "What Tab remembered".
4. **Live trigger (15 s):** Settings, Demo controls, "Simulate a client message" (for example "Could you also
   make a banner for our newsletter?"). It appears on the Acme page tagged "Simulated" and gets decided.
   With live Slack configured, post in the channel instead.
5. **No human raises the bill (20 s):** Settings, "Jump to 1 Nov 09:00". The activity feed shows "Raised invoice
   for Acme Outdoor Ltd: £487.50, 5 billable lines, 3 favours". Open the invoice in the Stripe test dashboard
   to show the £0 "On the house" lines.
6. **Proof + dispute (20 s):** open the proof page from the client page, question the Careers line and show the
   upheld reply. Pay with test card `4242 4242 4242 4242` (any future date, any CVC). Within 60 s the status
   turns "paid" (polling).
7. **Memory (10 s):** Memory page, "Refresh graph", then Ask Tab: "Why did you bill Acme £200?"
8. **Close (10 s):** the Acme health panel: "Over scope", with the recommendation paragraph.

## Known limitations

See `REPORT.md` sections 7–10. In short: everything that needs the LLM or Stripe is built but is only verified
once keys are added; live Slack and IMAP are written but untested.
