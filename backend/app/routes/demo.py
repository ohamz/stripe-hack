"""Demo controls: clock, simulated messages, reset, manual triggers. Clearly labelled in the UI."""

from __future__ import annotations

import asyncio
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.clock import get_now, parse_aware, period_of, set_demo_now
from app.db import get_session, session_scope
from app.events import emit
from app.ingest import IngestReport, store_item
from app.connectors import RawItem
from app.routes.common import client_or_404
from app.schemas import ClockBody, SimulateBody, iso

router = APIRouter(prefix="/api/demo")


def _busy_guard() -> None:
    from app.main import state

    if state.get("busy"):
        raise HTTPException(409, f"Busy: {state['busy']}")


async def _run_billing_now() -> list[dict]:
    from app.billing.invoicer import run_billing_job

    with session_scope() as session:
        return await run_billing_job(session)


async def _run_pipeline_now(reason: str) -> None:
    from app.agent.pipeline import run_pipeline

    with session_scope() as session:
        await run_pipeline(session, reason=reason)


@router.post("/clock")
async def set_clock(body: ClockBody, session: Session = Depends(get_session)) -> dict:
    try:
        value = parse_aware(body.now) if body.now else None
    except ValueError as exc:
        raise HTTPException(400, f"Bad datetime: {exc}") from exc
    set_demo_now(session, value)
    now = get_now(session)
    emit(session, "clock", f"Demo clock set to {now.isoformat()}" if value else "Demo clock cleared (real time).",
         now=now.isoformat())
    asyncio.get_running_loop().create_task(_run_billing_now())  # don't wait up to 30 s for the next tick
    return {"now": iso(now), "period": period_of(now)}


@router.post("/simulate")
async def simulate(body: SimulateBody, session: Session = Depends(get_session)) -> dict:
    client = client_or_404(session, body.client_slug)
    now = get_now(session)
    raw = RawItem(
        source="simulated",
        external_id=f"sim-{secrets.token_hex(6)}",
        occurred_at=now,
        author=client.contact_name,
        title=f"Simulated {body.channel} message",
        text=body.text.strip(),
        raw={"channel": body.channel, "simulated": True, "text": body.text.strip()},
        hints={"client_slug": client.slug},
    )
    item = store_item(session, raw, client, IngestReport())
    emit(session, "simulated", f"Simulated {body.channel} message from {client.contact_name} ({client.name}).",
         client=client.slug, source_item_id=item.id)
    asyncio.get_running_loop().create_task(_run_pipeline_now("simulated message"))
    return {"source_item_id": item.id}


@router.post("/reset")
async def reset_demo() -> dict:
    from app.main import state
    from app.seed import reset_all, seed

    _busy_guard()
    state["busy"] = "Resetting the demo"

    async def _go() -> None:
        try:
            notes = await reset_all()
            state["busy"] = "Seeding the demo"
            ingest, report, seconds = await seed()
            with session_scope() as s:
                for n in notes:
                    emit(s, "reset", n)
                emit(s, "seeded", f"Demo reset and seeded in {seconds:.0f} s.", seconds=round(seconds, 1),
                     skipped=report.skipped_reason, errors=report.errors)
        except Exception as exc:
            with session_scope() as s:
                emit(s, "reset_error", f"Reset failed: {type(exc).__name__}: {exc}", level="error")
        finally:
            state["busy"] = None

    asyncio.get_running_loop().create_task(_go())
    return {"started": True}


@router.post("/run-pipeline")
async def run_pipeline_endpoint() -> dict:
    _busy_guard()
    asyncio.get_running_loop().create_task(_run_pipeline_now("manual"))
    return {"started": True}


@router.post("/run-billing")
async def run_billing_endpoint() -> dict:
    _busy_guard()
    return {"results": await _run_billing_now()}
