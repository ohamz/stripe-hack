"""Optional live IMAP poller. Only runs if IMAP_HOST, IMAP_USER and IMAP_PASSWORD are set.

Not tested in this build (no credentials were provided); see REPORT.md.
"""

from __future__ import annotations

import imaplib
import json
from email import policy
from email.parser import BytesParser

from sqlmodel import Session

from app.clock import get_setting, set_setting
from app.config import get_settings
from app.connectors import RawItem
from app.connectors.email_files import email_to_item
from app.models import utcnow


def poll_imap(session: Session) -> list[RawItem]:
    s = get_settings()
    if not (s.imap_host and s.imap_user and s.imap_password):
        return []
    items: list[RawItem] = []
    try:
        last_uid = int(get_setting(session, "last_imap_uid", "0") or 0)
        with imaplib.IMAP4_SSL(s.imap_host) as conn:
            conn.login(s.imap_user, s.imap_password)
            conn.select("INBOX", readonly=True)
            typ, data = conn.uid("search", None, f"UID {last_uid + 1}:*")
            if typ != "OK":
                raise RuntimeError(f"IMAP search failed: {typ}")
            uids = [int(u) for u in (data[0] or b"").split() if int(u) > last_uid]
            for uid in uids:
                typ, msg_data = conn.uid("fetch", str(uid), "(RFC822)")
                if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                    continue
                msg = BytesParser(policy=policy.default).parsebytes(msg_data[0][1])
                items.append(email_to_item(msg, fallback_id=f"imap-uid-{uid}"))
                last_uid = max(last_uid, uid)
        set_setting(session, "last_imap_uid", str(last_uid))
        set_setting(session, "connector:email", json.dumps({"state": "live", "last_ok": utcnow().isoformat()}))
    except Exception as exc:
        set_setting(session, "connector:email", json.dumps({"state": "error", "error": f"{type(exc).__name__}: {exc}",
                                                            "at": utcnow().isoformat()}))
        return []
    return items
