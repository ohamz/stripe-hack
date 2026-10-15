"""Demo Slack export loader: a JSON list of {ts, user, user_name, channel, text}."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.connectors import RawItem


def slack_message_to_item(msg: dict) -> RawItem:
    ts = str(msg["ts"])
    channel = msg.get("channel", "")
    return RawItem(
        source="slack",
        external_id=f"{channel}:{ts}",
        occurred_at=datetime.fromtimestamp(float(ts), tz=timezone.utc),
        author=msg.get("user_name") or msg.get("user", ""),
        title=None,
        text=msg.get("text", ""),
        raw=msg,
        hints={"slack_channel": channel, "user_name": msg.get("user_name", "")},
    )


def load_slack_file(path: Path) -> list[RawItem]:
    messages = json.loads(path.read_text(encoding="utf-8"))
    return [slack_message_to_item(m) for m in messages]


def load_slack_dir(directory: Path) -> list[RawItem]:
    items: list[RawItem] = []
    for path in sorted(directory.glob("*.json")):
        items.extend(load_slack_file(path))
    return items
