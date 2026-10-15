"""Reset and seed the demo (shared by `make reset`, `make seed` and the Settings "Reset demo" button)."""

from __future__ import annotations

import shutil
import time
from datetime import datetime

from sqlmodel import SQLModel

from app.agent.pipeline import PipelineReport, run_pipeline
from app.clock import LONDON, START_PERIOD_KEY, set_demo_now, set_setting
from app.config import BACKEND_DIR, VAR_DIR
from app.db import get_engine, init_db, session_scope
from app.events import emit
from app.ingest import IngestReport, load_demo_sources
from app.memory import cognee_client

DEMO_NOW = datetime(2026, 10, 31, 18, 0, tzinfo=LONDON)
DEMO_START_PERIOD = "2026-10"  # Tab started keeping the tab in October; September is history (memory only).


async def reset_all() -> list[str]:
    """Wipe SQLite and Cognee memory. Returns human-readable notes about what happened."""
    notes: list[str] = []
    from app import models  # noqa: F401

    engine = get_engine()
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    notes.append("SQLite tables dropped and recreated.")
    try:
        result = await cognee_client.forget_everything()
        notes.append(f"Cognee memory wiped with cognee.forget(everything=True): {result}")
    except Exception as exc:
        notes.append(f"cognee.forget(everything=True) failed: {type(exc).__name__}: {exc}")
        cognee_dir = BACKEND_DIR / ".cognee"
        if cognee_dir.exists():
            shutil.rmtree(cognee_dir)
            notes.append(f"Removed Tab's local Cognee folder {cognee_dir} instead.")
    if VAR_DIR.exists():
        shutil.rmtree(VAR_DIR)
    return notes


async def seed() -> tuple[IngestReport, PipelineReport, float]:
    init_db()
    started = time.monotonic()
    with session_scope() as session:
        set_demo_now(session, DEMO_NOW)
        set_setting(session, START_PERIOD_KEY, DEMO_START_PERIOD)
        ingest = load_demo_sources(session)
        emit(session, "ingested", f"Loaded the demo files: {sum(ingest.created.values())} new source items "
             f"({', '.join(f'{v} {k}' for k, v in sorted(ingest.created.items()))}), {ingest.unassigned} unassigned.",
             created=ingest.created, unassigned=ingest.unassigned)
        report = await run_pipeline(session, reason="seed")
    return ingest, report, time.monotonic() - started
