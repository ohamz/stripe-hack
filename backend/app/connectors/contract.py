"""Contract loader (PDF or Markdown) and goodwill rules loader."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from app.clock import LONDON
from app.connectors import RawItem

_CLAUSE_RE = re.compile(r"^\s*(?:[-*]\s*)?(\d+\.\d+)\s+(.*)$")
_HEADING_RE = re.compile(r"^\s*(?:#+\s*)?\d+\.\s+\S")
_SIGNED_RE = re.compile(r"Signed\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})")


def read_contract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    return path.read_text(encoding="utf-8").replace("**", "").strip()


def parse_clauses(text: str) -> dict[str, str]:
    """Numbered clauses ("2.1 ...") from contract text, joining wrapped lines. Deterministic."""
    clauses: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        m = _CLAUSE_RE.match(stripped)
        if m:
            current = m.group(1)
            clauses[current] = m.group(2).strip()
        elif not stripped or _HEADING_RE.match(stripped) or stripped.startswith("#"):
            current = None
        elif current is not None:
            clauses[current] += " " + stripped
    return clauses


def _signed_at(text: str, path: Path) -> datetime:
    m = _SIGNED_RE.search(text)
    if m:
        return datetime.strptime(m.group(1), "%d %B %Y").replace(tzinfo=LONDON).astimezone(timezone.utc)
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def load_contract(path: Path, client_slug: str) -> RawItem:
    """Prefer the configured file; if a PDF is configured but missing, use the .md next to it."""
    if not path.exists() and path.with_suffix(".md").exists():
        path = path.with_suffix(".md")
    text = read_contract_text(path)
    if not text:
        raise ValueError(f"{path.name}: no text could be extracted")
    return RawItem(
        source="contract",
        external_id=f"{client_slug}:{path.name}",
        occurred_at=_signed_at(text, path),
        author="contract",
        title=path.name,
        text=text,
        raw={"file": path.name, "clauses": parse_clauses(text)},
        hints={"client_slug": client_slug},
    )


_RULE_HEADING_RE = re.compile(r"^##\s+(G\d+)\s*$")
_APPLIES_RE = re.compile(r"^Applies to:\s*(.+)$", re.IGNORECASE)


def parse_goodwill_rules(text: str) -> list[dict]:
    """Parse goodwill_rules.md into [{rule_ref, applies_to: "all" | [slugs], text}]."""
    rules: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        stripped = line.strip()
        heading = _RULE_HEADING_RE.match(stripped)
        if heading:
            current = {"rule_ref": heading.group(1), "applies_to": None, "lines": []}
            rules.append(current)
            continue
        if current is None or not stripped:
            continue
        applies = _APPLIES_RE.match(stripped)
        if applies and current["applies_to"] is None:
            value = applies.group(1).strip()
            current["applies_to"] = "all" if value.lower() in ("all", "all clients") else [s.strip() for s in value.split(",") if s.strip()]
        else:
            current["lines"].append(stripped)
    out = []
    for r in rules:
        if r["applies_to"] is None:
            raise ValueError(f"goodwill rule {r['rule_ref']} has no 'Applies to:' line")
        out.append({"rule_ref": r["rule_ref"], "applies_to": r["applies_to"], "text": " ".join(r["lines"]).strip()})
    return out


def load_goodwill_rules(path: Path) -> list[dict]:
    return parse_goodwill_rules(path.read_text(encoding="utf-8"))
