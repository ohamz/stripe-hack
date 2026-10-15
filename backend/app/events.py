"""Agent activity log (AgentEvent rows shown in the live feed)."""

from __future__ import annotations

import logging
from typing import Any

from sqlmodel import Session

from app.models import AgentEvent

log = logging.getLogger("tab")


def emit(session: Session, type: str, message: str, level: str = "info", **payload: Any) -> AgentEvent:
    event = AgentEvent(level=level, type=type, message=message, payload_json=payload)
    session.add(event)
    session.commit()
    getattr(log, {"warn": "warning"}.get(level, level))("[%s] %s", type, message)
    return event
