"""Thin wrapper around the Cognee v1.x API: remember, recall, forget, visualize.

Checked against the installed cognee (1.6.4) source:
- cognee.remember(data, dataset_name=..., *, self_improvement=..., node_set=...)  (node_set goes via **kwargs)
- cognee.recall(query_text, query_type, *, datasets, node_name, top_k, include_references) -> list of Pydantic objects
- RecallPreconditionError is not an importable class: it is a CogneeValidationError whose .name is
  "RecallPreconditionError".
- cognee.forget(everything=True)
- cognee.visualize_graph(destination_file_path, ..., dataset=...) -> HTML string
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import app.config  # noqa: F401  (sets Cognee env vars before cognee is imported)
from app.config import llm_key_status

CONTEXT_LIMIT = 4000

# PLAN.md 7.3: self_improvement=False while seeding unless measured fast enough. Overridable.
SELF_IMPROVEMENT = os.environ.get("TAB_COGNEE_SELF_IMPROVEMENT", "false").lower() in ("1", "true", "yes")

# Local Cognee stores are file-based; serialise access from this process.
_lock = asyncio.Lock()


class LLMKeyMissing(RuntimeError):
    pass


class MemoryEmpty(RuntimeError):
    """recall() was called before anything was remembered (Cognee's RecallPreconditionError), or the graph
    for the requested datasets isn't built yet (a source="system" memory_warming_up / build_failed marker)."""


def require_llm() -> None:
    status = llm_key_status()
    if not status.ok:
        raise LLMKeyMissing(status.message)


def _cognee():
    import cognee

    return cognee


@dataclass
class RecallOutcome:
    query: str
    query_type: str
    datasets: list[str]
    node_name: list[str] | None
    answer: str
    evidence_block: str
    references: list[dict[str, Any]] = field(default_factory=list)
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _split_evidence(text: str) -> tuple[str, str]:
    marker = "Evidence:"
    idx = text.find("\n" + marker)
    if idx == -1 and text.startswith(marker):
        idx = 0
    if idx == -1:
        return text.strip(), ""
    return text[:idx].strip(), text[idx:].strip()


async def remember(records: list[str], dataset: str, node_set: list[str]) -> dict[str, Any]:
    """Store records permanently in one Cognee call (batched per client per source)."""
    require_llm()
    if not records:
        return {"status": "skipped", "elapsed_seconds": 0.0, "count": 0}
    cognee = _cognee()
    started = time.monotonic()
    async with _lock:
        result = await cognee.remember(
            records,
            dataset_name=dataset,
            node_set=node_set,
            self_improvement=SELF_IMPROVEMENT,
        )
    return {
        "status": str(getattr(result, "status", "unknown")),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "count": len(records),
        "improve_error": str(getattr(result, "improve_error", "") or "") or None,
    }


async def recall(
    query: str,
    datasets: list[str],
    query_type: str = "GRAPH_COMPLETION",
    node_name: list[str] | None = None,
    top_k: int | None = None,
) -> RecallOutcome:
    require_llm()
    cognee = _cognee()
    from cognee import SearchType
    from cognee.exceptions import CogneeValidationError

    kwargs: dict[str, Any] = {"datasets": datasets, "include_references": True}
    if node_name:
        kwargs["node_name"] = node_name
    if top_k:
        kwargs["top_k"] = top_k
    try:
        async with _lock:
            results = await cognee.recall(query, query_type=SearchType[query_type], **kwargs)
    except CogneeValidationError as exc:
        if getattr(exc, "name", "") == "RecallPreconditionError":
            raise MemoryEmpty(str(exc)) from exc
        raise

    results = list(results or [])
    markers = [r for r in results if getattr(r, "source", None) == "system"]
    if markers:
        m = markers[0]
        raise MemoryEmpty(f"{getattr(m, 'status', 'system')}: {getattr(m, 'text', '')}")
    texts: list[str] = []
    references: list[dict[str, Any]] = []
    for r in results:
        if getattr(r, "source", "graph") != "graph":
            continue  # only permanent-graph answers count as memory here
        texts.append(str(getattr(r, "text", "") or ""))
        metadata = getattr(r, "metadata", None) or {}
        evidence = metadata.get("evidence") if isinstance(metadata, dict) else None
        for ev in evidence or []:
            references.append(ev if isinstance(ev, dict) else getattr(ev, "model_dump", lambda: {"value": str(ev)})())
    full = "\n\n".join(t for t in texts if t)
    answer, evidence_block = _split_evidence(full)
    return RecallOutcome(
        query=query,
        query_type=query_type,
        datasets=datasets,
        node_name=node_name,
        answer=answer,
        evidence_block=evidence_block,
        references=references,
        context=full[:CONTEXT_LIMIT],
    )


async def wait_for_background_tasks() -> None:
    """Cognee docs: scripts should wait for background tasks before exiting."""
    import sys

    if "cognee" in sys.modules:
        from cognee import wait_for_background_tasks as wait

        await wait()


async def forget_everything() -> dict[str, Any]:
    cognee = _cognee()
    async with _lock:
        return await cognee.forget(everything=True)


async def visualize(dataset: str, destination: Path) -> str:
    """Render the dataset's graph to an HTML file and return the HTML."""
    cognee = _cognee()
    destination.parent.mkdir(parents=True, exist_ok=True)
    async with _lock:
        return await cognee.visualize_graph(destination_file_path=str(destination), dataset=dataset)


def dataset_for(slug: str) -> str:
    return f"client_{slug}"
