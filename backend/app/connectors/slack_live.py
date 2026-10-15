"""Optional live Slack poller (Web API conversations.history). Only runs if SLACK_BOT_TOKEN and SLACK_CHANNEL_IDS are set.

Not tested in this build (no credentials were provided); see REPORT.md.
Connector status is recorded honestly: "live" only after a successful poll.
"""

from __future__ import annotations

import json

import httpx
from sqlmodel import Session

from app.clock import get_setting, set_setting
from app.config import get_settings
from app.connectors import RawItem
from app.connectors.slack_file import slack_message_to_item
from app.models import utcnow

API = "https://slack.com/api"


def _get(client: httpx.Client, method: str, **params) -> dict:
    resp = client.get(f"{API}/{method}", params=params)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack {method} error: {data.get('error')}")
    return data


def poll_slack(session: Session) -> list[RawItem]:
    settings = get_settings()
    if not (settings.slack_bot_token and settings.slack_channel_ids):
        return []
    items: list[RawItem] = []
    try:
        with httpx.Client(headers={"Authorization": f"Bearer {settings.slack_bot_token}"}, timeout=15) as client:
            user_names: dict[str, str] = {}
            for channel_id in settings.slack_channel_ids:
                channel_name = _get(client, "conversations.info", channel=channel_id)["channel"]["name"]
                key = f"last_slack_ts:{channel_id}"
                oldest = get_setting(session, key, "0")
                history = _get(client, "conversations.history", channel=channel_id, oldest=oldest, limit=200)
                newest = oldest
                for msg in sorted(history.get("messages", []), key=lambda m: float(m["ts"])):
                    if msg.get("subtype") or float(msg["ts"]) <= float(oldest):
                        continue
                    uid = msg.get("user", "")
                    if uid and uid not in user_names:
                        user = _get(client, "users.info", user=uid)["user"]
                        user_names[uid] = user.get("real_name") or user.get("name") or uid
                    items.append(slack_message_to_item({"ts": msg["ts"], "user": uid, "user_name": user_names.get(uid, uid),
                                                        "channel": channel_name, "text": msg.get("text", "")}))
                    newest = msg["ts"]
                set_setting(session, key, newest)
        set_setting(session, "connector:slack", json.dumps({"state": "live", "last_ok": utcnow().isoformat()}))
    except Exception as exc:
        set_setting(session, "connector:slack", json.dumps({"state": "error", "error": f"{type(exc).__name__}: {exc}",
                                                            "at": utcnow().isoformat()}))
        return []
    return items
