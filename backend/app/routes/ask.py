from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.memory.cognee_client import LLMKeyMissing, MemoryEmpty
from app.routes.common import client_or_404
from app.schemas import AskBody

router = APIRouter(prefix="/api")


@router.post("/ask")
async def ask_tab(body: AskBody, session: Session = Depends(get_session)) -> dict:
    from app.agent.explain import ask

    client = client_or_404(session, body.client_slug) if body.client_slug else None
    try:
        return await ask(session, body.question.strip(), client)
    except LLMKeyMissing as exc:
        raise HTTPException(503, str(exc)) from exc
    except MemoryEmpty as exc:
        raise HTTPException(409, f"Memory is empty: {exc}") from exc
    except Exception as exc:
        raise HTTPException(502, f"Recall failed: {type(exc).__name__}: {exc}") from exc
