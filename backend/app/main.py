"""FastAPI app and background workers (PLAN.md section 4)."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import assert_safe_to_start, get_settings, llm_key_status, stripe_key_status
from app.db import init_db, session_scope

log = logging.getLogger("tab")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BILLING_EVERY = 30
POLL_PAYMENTS_EVERY = 60
LIVE_SOURCES_EVERY = 30

state: dict = {"busy": None, "stripe_account": None}


async def _billing_loop() -> None:
    from app.billing.invoicer import run_billing_job

    while True:
        if state["busy"] is None:
            try:
                with session_scope() as session:
                    await run_billing_job(session)
            except Exception:
                log.exception("billing job failed")
        await asyncio.sleep(BILLING_EVERY)


async def _payment_poll_loop() -> None:
    from app.billing.webhooks import poll_open_invoices

    while True:
        await asyncio.sleep(POLL_PAYMENTS_EVERY)
        try:
            with session_scope() as session:
                await poll_open_invoices(session)
        except Exception:
            log.exception("payment polling failed")


async def _live_sources_loop() -> None:
    from app.agent.pipeline import run_pipeline
    from app.connectors.email_imap import poll_imap
    from app.connectors.slack_live import poll_slack
    from app.ingest import ingest_raw_items, registry, sync_clients

    while True:
        try:
            with session_scope() as session:
                raw = await asyncio.to_thread(poll_slack, session) + await asyncio.to_thread(poll_imap, session)
                if raw:
                    reg = registry()
                    report = ingest_raw_items(session, raw, reg, sync_clients(session, reg))
                    if report.new_item_ids:
                        await run_pipeline(session, reason="live sources")
        except Exception:
            log.exception("live source polling failed")
        await asyncio.sleep(LIVE_SOURCES_EVERY)


def _check_stripe_account() -> dict:
    from app.billing.stripe_client import account_summary

    try:
        return {"ok": True, **account_summary()}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_safe_to_start()  # refuses a live (non sk_test_) Stripe key; an empty key only disables billing
    init_db()
    settings = get_settings()
    log.info("LLM: %s", llm_key_status().message)
    log.info("Stripe: %s", stripe_key_status().message)
    tasks = [asyncio.create_task(_billing_loop())]
    if stripe_key_status().ok:
        state["stripe_account"] = await asyncio.to_thread(_check_stripe_account)
        log.info("Stripe account check: %s", json.dumps(state["stripe_account"]))
        if not settings.stripe_webhook_secret:
            tasks.append(asyncio.create_task(_payment_poll_loop()))
    if settings.slack_bot_token or settings.imap_host:
        tasks.append(asyncio.create_task(_live_sources_loop()))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Tab", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

from app.routes import ask, clients, demo, invoices, memory, overview, proof, settings as settings_routes  # noqa: E402

for module in (overview, clients, invoices, proof, ask, memory, settings_routes, demo):
    app.include_router(module.router)
