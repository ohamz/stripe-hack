"""Demo email loader: RFC 822 .eml files with a plain-text body."""

from __future__ import annotations

from datetime import timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

from app.connectors import RawItem


def _plain_body(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain",))
    if part is None:
        return ""
    return part.get_content().strip()


def email_to_item(msg: EmailMessage, fallback_id: str) -> RawItem:
    from_pairs = getaddresses([msg.get("From", "")])
    from_name, from_email = from_pairs[0] if from_pairs else ("", "")
    to_emails = [addr.lower() for _, addr in getaddresses(msg.get_all("To", []) + msg.get_all("Cc", [])) if addr]
    message_id = (msg.get("Message-ID") or fallback_id).strip().strip("<>")
    occurred = parsedate_to_datetime(msg["Date"]).astimezone(timezone.utc)
    subject = msg.get("Subject", "")
    return RawItem(
        source="email",
        external_id=message_id,
        occurred_at=occurred,
        author=from_name or from_email,
        title=subject,
        text=_plain_body(msg),
        raw={
            "from": msg.get("From", ""),
            "to": msg.get("To", ""),
            "subject": subject,
            "date": msg.get("Date", ""),
            "message_id": message_id,
        },
        hints={"from_email": from_email.lower(), "to_emails": to_emails},
    )


def load_eml(path: Path) -> RawItem:
    with path.open("rb") as fh:
        msg = BytesParser(policy=policy.default).parse(fh)
    return email_to_item(msg, fallback_id=path.name)


def load_email_dir(directory: Path) -> list[RawItem]:
    return [load_eml(p) for p in sorted(directory.glob("*.eml"))]
