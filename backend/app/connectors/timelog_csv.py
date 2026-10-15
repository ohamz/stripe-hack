"""Time tracker CSV loader (Toggl-like): date,start_time,duration_minutes,client,project,description."""

from __future__ import annotations

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.clock import LONDON
from app.connectors import RawItem

REQUIRED_COLUMNS = ["date", "start_time", "duration_minutes", "client", "project", "description"]


def row_to_item(row: dict[str, str], author: str) -> RawItem:
    start = datetime.fromisoformat(f"{row['date']}T{row['start_time']}").replace(tzinfo=LONDON)
    minutes = int(row["duration_minutes"])
    if minutes <= 0:
        raise ValueError(f"duration_minutes must be positive: {row}")
    client = (row.get("client") or "").strip()
    digest = hashlib.sha1(f"{client}|{row['project']}|{row['description']}".encode()).hexdigest()[:10]
    return RawItem(
        source="timelog",
        external_id=f"{row['date']}T{row['start_time']}:{digest}",
        occurred_at=start.astimezone(timezone.utc),
        author=author,
        title=row["project"],
        text=f"{minutes} min logged: {row['description']}",
        raw={k: row.get(k, "") for k in REQUIRED_COLUMNS},
        hints={"timetracker_client": client},
    )


def load_timelog_csv(path: Path, author: str = "Maya Chen") -> list[RawItem]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name}: missing columns {missing}")
        return [row_to_item(row, author) for row in reader]


def load_timelog_dir(directory: Path, author: str = "Maya Chen") -> list[RawItem]:
    items: list[RawItem] = []
    for path in sorted(directory.glob("*.csv")):
        items.extend(load_timelog_csv(path, author))
    return items
