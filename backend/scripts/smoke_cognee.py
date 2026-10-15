"""Phase 0 smoke test (a): cognee.remember + cognee.recall round trip on one sentence.

Uses a throwaway dataset ('tab_smoke_test') and deletes it afterwards. Needs LLM_API_KEY.
"""

import asyncio
import importlib.metadata as md
import sys
import time

import _path  # noqa: F401

from app.config import llm_key_status

DATASET = "tab_smoke_test"
SENTENCE = "Maya Chen designed the Careers page for Acme Outdoor Ltd on 22 October 2026."


async def main() -> int:
    print(f"python {sys.version.split()[0]}, cognee {md.version('cognee')}")
    status = llm_key_status()
    if not status.ok:
        print(f"SKIPPED: {status.message}")
        return 2
    import cognee
    from cognee import SearchType

    t = time.monotonic()
    result = await cognee.remember(SENTENCE, dataset_name=DATASET, self_improvement=False)
    print(f"remember(): status={getattr(result, 'status', '?')} in {time.monotonic() - t:.1f} s")
    t = time.monotonic()
    answers = await cognee.recall("Which page did Maya design for Acme?", query_type=SearchType.GRAPH_COMPLETION,
                                  datasets=[DATASET], include_references=True)
    print(f"recall(): {len(answers)} result(s) in {time.monotonic() - t:.1f} s; type {type(answers[0]).__name__ if answers else '-'}")
    text = " ".join(getattr(a, "text", "") or "" for a in answers)
    print("answer:", text[:500])
    try:
        await cognee.forget(dataset=DATASET)
        print("cleanup: forget(dataset=...) ok")
    except Exception as exc:
        print(f"cleanup failed: {type(exc).__name__}: {exc}")
    await cognee.wait_for_background_tasks()
    ok = "careers" in text.lower()
    print("PASS" if ok else "FAIL: answer does not mention the Careers page")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
