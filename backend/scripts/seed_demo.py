"""make seed: load demo data end to end and run the pipeline (demo clock 2026-10-31 18:00 Europe/London)."""

import asyncio

import _path  # noqa: F401

from app.memory import cognee_client
from app.seed import seed


async def main() -> int:
    ingest, report, seconds = await seed()
    print(f"Ingested: {dict(sorted(ingest.created.items()))} new, {ingest.existing} already present, "
          f"{ingest.unassigned} unassigned")
    if report.skipped_reason:
        print(f"PIPELINE PAUSED: {report.skipped_reason}")
        print("Demo files are loaded. Memory, contract terms, extraction and decisions need the LLM key.")
    else:
        print(f"Remembered: {report.remembered} (Cognee remember() time {report.remember_seconds:.1f} s)")
        print(f"Requests created: {report.requests_created}; time entries matched: {report.time_entries_matched}; "
              f"decisions: {report.decisions_made}")
    for e in report.errors:
        print("ERROR:", e)
    print(f"Seed finished in {seconds:.1f} s")
    await cognee_client.wait_for_background_tasks()
    # Exit 0 when only the LLM key is missing (files are loaded, pipeline paused with a clear message).
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
