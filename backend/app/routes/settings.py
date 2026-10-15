from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.clock import DEMO_NOW_KEY, get_now, get_setting
from app.config import get_settings, llm_key_status, stripe_key_status
from app.db import get_session, session_scope
from app.events import emit
from app.models import Client, GoodwillRule, Invoice, SourceItem
from app.routes.common import display_period
from app.schemas import RuleBody, iso, rule_out

router = APIRouter(prefix="/api/settings")


def _connector(session: Session, name: str, configured: bool, demo_source: str) -> dict:
    demo_count = len(session.exec(select(SourceItem).where(SourceItem.source == demo_source)).all())
    if configured:
        status = json.loads(get_setting(session, f"connector:{name}", "null") or "null")
        if status and status.get("state") == "live":
            return {"mode": "Live", "detail": f"Last successful poll {status.get('last_ok')}"}
        if status and status.get("state") == "error":
            return {"mode": "Error", "detail": status.get("error")}
        return {"mode": "Connecting", "detail": "Credentials set; no successful poll yet."}
    if demo_count:
        return {"mode": "Demo file", "detail": f"{demo_count} items loaded from demo_data"}
    return {"mode": "Off", "detail": "Not configured"}


@router.get("")
def get_settings_page(session: Session = Depends(get_session)) -> dict:
    from app.main import state

    s = get_settings()
    clients = {c.id: c for c in session.exec(select(Client)).all()}
    stripe_status = stripe_key_status()
    account = state.get("stripe_account")
    if stripe_status.ok and account and account.get("ok"):
        stripe_info = {"mode": "Test mode connected", "detail": f"Account {account.get('id')}"}
    elif stripe_status.ok and account:
        stripe_info = {"mode": "Error", "detail": account.get("error")}
    elif stripe_status.ok:
        stripe_info = {"mode": "Test key set", "detail": "Account not checked yet (restart the API)."}
    else:
        stripe_info = {"mode": "Off", "detail": stripe_status.message}
    count = lambda src: len(session.exec(select(SourceItem).where(SourceItem.source == src)).all())  # noqa: E731
    llm = llm_key_status()
    return {
        "integrations": {
            "slack": _connector(session, "slack", bool(s.slack_bot_token and s.slack_channel_ids), "slack"),
            "email": _connector(session, "email", bool(s.imap_host and s.imap_user and s.imap_password), "email"),
            "calendar": {"mode": "File", "detail": f"{count('calendar')} events from demo_data/calendar"},
            "timelog": {"mode": "File", "detail": f"{count('timelog')} entries from demo_data/timelog"},
            "stripe": stripe_info,
            "llm": {"mode": "Configured" if llm.ok else "Missing", "detail": llm.message},
            "payments": {"mode": "Webhooks" if s.stripe_webhook_secret else "Polling every 60 s", "detail": ""},
        },
        "rules": [rule_out(r, clients) for r in session.exec(select(GoodwillRule).order_by(GoodwillRule.rule_ref)).all()],
        "clock": {"now": iso(get_now(session)), "demo_now": get_setting(session, DEMO_NOW_KEY)},
        "clients": [{"slug": c.slug, "name": c.name} for c in clients.values()],
    }


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, body: RuleBody, session: Session = Depends(get_session)) -> dict:
    from app.agent.pipeline import redecide_open_period, run_pipeline
    from app.agent.terms import parse_goodwill_rule

    rule = session.get(GoodwillRule, rule_id)
    if rule is None:
        raise HTTPException(404, "No such rule")
    changed = False
    if body.text is not None and body.text.strip() != rule.text:
        rule.text, rule.params_json, rule.parse_status, rule.parse_note = body.text.strip(), None, "pending", None
        changed = True
    if body.enabled is not None and body.enabled != rule.enabled:
        rule.enabled = body.enabled
        changed = True
    session.add(rule)
    session.commit()
    clients = {c.id: c for c in session.exec(select(Client)).all()}
    if not changed:
        return {"rule": rule_out(rule, clients), "redecided": 0}
    if not llm_key_status().ok:
        emit(session, "rule_saved", f"Goodwill rule {rule.rule_ref} saved. {llm_key_status().message}, so it can't be "
             "re-parsed or applied yet; existing decisions are unchanged.", level="warn", rule=rule.rule_ref)
        return {"rule": rule_out(rule, clients), "redecided": 0}
    if rule.parse_status == "pending":
        await parse_goodwill_rule(session, rule)
    period = display_period(session)
    if session.exec(select(Invoice).where(Invoice.period == period)).first():
        emit(session, "rule_saved", f"Rule {rule.rule_ref} saved. Invoiced periods are never re-decided.", rule=rule.rule_ref)
    dropped = await redecide_open_period(session, period)
    emit(session, "rule_saved", f"Goodwill rule {rule.rule_ref} changed: re-deciding {dropped} request(s) for {period}.",
         rule=rule.rule_ref)

    async def _rerun() -> None:
        with session_scope() as s2:
            await run_pipeline(s2, reason=f"rule {rule.rule_ref} edited")

    asyncio.get_running_loop().create_task(_rerun())
    return {"rule": rule_out(rule, clients), "redecided": dropped}
