"""Calendar loader: one SourceItem per VEVENT in an .ics file."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from icalendar import Calendar

from app.clock import LONDON
from app.connectors import RawItem


def _aware(value) -> datetime:  # noqa: ANN001
    if not isinstance(value, datetime):
        raise ValueError(f"all-day events are not supported: {value!r}")
    if value.tzinfo is None:
        value = value.replace(tzinfo=LONDON)
    return value


def _attendees(component) -> list[tuple[str, str]]:  # noqa: ANN001
    raw = component.get("ATTENDEE")
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    out = []
    for v in values:
        email = str(v).replace("mailto:", "").replace("MAILTO:", "").strip().lower()
        name = str(v.params.get("CN", "")) if hasattr(v, "params") else ""
        out.append((name, email))
    return out


def load_ics(path: Path) -> list[RawItem]:
    cal = Calendar.from_ical(path.read_bytes())
    items: list[RawItem] = []
    for ev in cal.walk("VEVENT"):
        uid = str(ev.get("UID"))
        title = str(ev.get("SUMMARY", ""))
        start = _aware(ev.decoded("DTSTART"))
        end = _aware(ev.decoded("DTEND"))
        minutes = int((end - start).total_seconds() // 60)
        attendees = _attendees(ev)
        organizer = ev.get("ORGANIZER")
        organizer_name = str(organizer.params.get("CN", "")) if organizer is not None and hasattr(organizer, "params") else ""
        att_text = ", ".join(f"{n} <{e}>" if n else e for n, e in attendees) or "none"
        local_start, local_end = start.astimezone(LONDON), end.astimezone(LONDON)
        text = (
            f"Meeting '{title}' on {local_start:%Y-%m-%d} from {local_start:%H:%M} to {local_end:%H:%M} "
            f"({minutes} min). Attendees: {att_text}."
        )
        items.append(
            RawItem(
                source="calendar",
                external_id=uid,
                occurred_at=start.astimezone(timezone.utc),
                author=organizer_name or "calendar",
                title=title,
                text=text,
                raw={
                    "uid": uid,
                    "summary": title,
                    "start": start.astimezone(timezone.utc).isoformat(),
                    "end": end.astimezone(timezone.utc).isoformat(),
                    "minutes": minutes,
                    "attendees": [{"name": n, "email": e} for n, e in attendees],
                },
                hints={"calendar_title": title, "attendee_emails": [e for _, e in attendees]},
            )
        )
    return items


def load_calendar_dir(directory: Path) -> list[RawItem]:
    items: list[RawItem] = []
    for path in sorted(directory.glob("*.ics")):
        items.extend(load_ics(path))
    return items
