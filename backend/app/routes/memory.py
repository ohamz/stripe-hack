from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.config import VAR_DIR, llm_key_status
from app.db import get_session
from app.events import emit
from app.memory import cognee_client
from app.models import Client, Decision, Dispute, Invoice, InvoiceLine, Request, SourceItem
from app.routes.common import client_or_404

router = APIRouter(prefix="/api/memory")
NODE_SETS = ["contract", "goodwill_rules", "slack", "email", "calendar", "timelog", "simulated", "decision", "invoice", "dispute"]


def _graph_path(slug: str):
    return VAR_DIR / f"graph_{slug}.html"


@router.get("/stats")
def stats(session: Session = Depends(get_session)) -> dict:
    """Records Tab has written to Cognee, per node set per client (from Tab's own log of remember() calls)."""
    out = []
    for client in session.exec(select(Client).order_by(Client.id)).all():
        counts: Counter = Counter()
        pending: Counter = Counter()
        for item in session.exec(select(SourceItem).where(SourceItem.client_id == client.id)).all():
            node = item.cognee_node_set[0] if item.cognee_node_set else item.source
            (counts if item.remembered_at else pending)[node] += 1
        decisions = session.exec(select(Decision, Request).where(Decision.request_id == Request.id,
                                                                 Request.client_id == client.id)).all()
        for d, _ in decisions:
            (counts if d.remembered_at else pending)["decision"] += 1
        for inv in session.exec(select(Invoice).where(Invoice.client_id == client.id)).all():
            if inv.status != "failed":
                (counts if inv.remembered_at else pending)["invoice"] += 1
            for line in session.exec(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)).all():
                for dis in session.exec(select(Dispute).where(Dispute.invoice_line_id == line.id)).all():
                    (counts if dis.remembered_at else pending)["dispute"] += 1
        out.append({"slug": client.slug, "name": client.name, "dataset": client.cognee_dataset,
                    "remembered": {k: counts.get(k, 0) for k in NODE_SETS},
                    "pending": {k: pending.get(k, 0) for k in NODE_SETS},
                    "graph_available": _graph_path(client.slug).exists()})
    return {"node_sets": NODE_SETS, "clients": out, "llm_ok": llm_key_status().ok}


@router.get("/graph.html")
def graph_html(client: str) -> FileResponse:
    path = _graph_path(client)
    if not path.exists():
        raise HTTPException(404, "No graph rendered yet. Press Refresh on the Memory page.")
    return FileResponse(path, media_type="text/html")


@router.post("/graph/refresh")
async def refresh_graph(client: str, session: Session = Depends(get_session)) -> dict:
    c = client_or_404(session, client)
    remembered = session.exec(select(SourceItem).where(SourceItem.client_id == c.id, SourceItem.remembered_at != None)).first()  # noqa: E711
    if remembered is None:
        raise HTTPException(409, "Nothing has been remembered for this client yet"
                            + ("" if llm_key_status().ok else f" ({llm_key_status().message})") + ".")
    try:
        await cognee_client.visualize(c.cognee_dataset, _graph_path(c.slug))
    except Exception as exc:
        emit(session, "memory_error", f"Graph render failed for {c.name}: {type(exc).__name__}: {exc}", level="error")
        raise HTTPException(502, f"Graph render failed: {type(exc).__name__}: {exc}") from exc
    return {"ok": True, "url": f"/api/memory/graph.html?client={c.slug}"}
