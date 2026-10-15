from app.agent.terms import ExtractedTerms, ParsedRule, validate_rule_params, validate_terms
from app.config import DEMO_DATA_DIR
from app.connectors.contract import load_goodwill_rules, parse_clauses, read_contract_text


def test_clauses_parsed_from_pdf_with_wrapped_lines():
    clauses = parse_clauses(read_contract_text(DEMO_DATA_DIR / "contracts" / "acme_contract.pdf"))
    assert set(clauses) == {"1.1", "2.1", "2.2", "2.3", "2.4", "3.1", "3.2", "3.3", "4.1", "4.2", "5.1", "5.2", "5.3", "5.4"}
    assert clauses["2.4"].endswith("is out of scope and billed under clause 5.")
    assert clauses["5.4"].endswith("Payment is due within 14 days.")


def test_pdf_and_markdown_agree():
    pdf = parse_clauses(read_contract_text(DEMO_DATA_DIR / "contracts" / "bright_bakery_contract.pdf"))
    md = parse_clauses(read_contract_text(DEMO_DATA_DIR / "contracts" / "bright_bakery_contract.md"))
    assert pdf == md


def test_goodwill_rules_file():
    rules = load_goodwill_rules(DEMO_DATA_DIR / "goodwill_rules.md")
    assert [(r["rule_ref"], r["applies_to"]) for r in rules] == [("G1", "all"), ("G2", ["acme"])]
    assert rules[0]["text"].startswith("Small favours that take under 20 minutes are free")


def test_rule_validation():
    ok = validate_rule_params(ParsedRule(type="small_favour", max_minutes_exclusive=20, max_per_month=2))
    assert ok == {"type": "small_favour", "max_minutes_exclusive": 20, "max_per_month": 2}
    assert validate_rule_params(ParsedRule(type="small_favour", max_minutes_exclusive=20)) is None
    typo = validate_rule_params(ParsedRule(type="always_free_kind", kind="typo_fix", counts_towards_allowance=False))
    assert typo == {"type": "always_free_kind", "kind": "typo_fix", "counts_towards_allowance": False}
    assert validate_rule_params(ParsedRule(type="always_free_kind", kind="typo_fix")) is None
    assert validate_rule_params(ParsedRule(type="not_understood")) is None


def _term(value, ref="2.1"):
    return {"value": value, "clause_ref": ref, "source_text": "t", "confidence": 0.9}


def test_terms_validation_reports_missing_and_bad_values():
    clauses = {"2.1": "", "3.2": "", "5.2": ""}
    extracted = ExtractedTerms.model_validate({
        "included_pages": _term(["Home"]), "revision_rounds_per_page": _term(2, "3.2"),
        "hourly_rate_pence": _term(0, "5.2"), "delivery_date": _term("30 Sept", "1.1"),
    })
    rows, missing, warnings = validate_terms(extracted, clauses)
    assert "included_pages" in rows and rows["included_pages"]["confidence"] == 0.9
    assert "hourly_rate_pence" in missing and "delivery_date" in missing and "meetings_per_month" in missing
    assert any("hourly_rate_pence" in w for w in warnings)


def test_terms_with_unknown_clause_get_low_confidence():
    rows, _, warnings = validate_terms(ExtractedTerms.model_validate({"included_pages": _term(["Home"], "9.9")}), {"2.1": ""})
    assert rows["included_pages"]["confidence"] == 0.5 and warnings
