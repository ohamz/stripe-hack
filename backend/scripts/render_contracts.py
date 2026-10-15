"""Render demo_data/contracts/*.md to PDF (the contract connector reads the PDF).

Run: .venv/bin/python scripts/render_contracts.py
The PDFs are committed, so this only needs re-running if a contract .md changes.
"""

import re
from pathlib import Path

from fpdf import FPDF

CONTRACTS = Path(__file__).resolve().parents[2] / "demo_data" / "contracts"


def render(md_path: Path) -> Path:
    pdf = FPDF(format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            pdf.ln(3)
            continue
        text = line.replace("**", "")
        if text.startswith("# "):
            pdf.set_font("Helvetica", "B", 16)
            pdf.multi_cell(0, 9, text[2:], new_x="LMARGIN", new_y="NEXT")
        elif text.startswith("## "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(0, 7, text[3:], new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, re.sub(r"^- ", "", text), new_x="LMARGIN", new_y="NEXT")
    out = md_path.with_suffix(".pdf")
    pdf.output(str(out))
    return out


if __name__ == "__main__":
    for md in sorted(CONTRACTS.glob("*.md")):
        print("wrote", render(md))
