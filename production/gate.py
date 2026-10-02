from __future__ import annotations

from typing import Any
from parsers.excel.menu_artifacts import classify_menu_token


def production_route(result: dict[str, Any], *, institution_id: str | None) -> str:
    if result.get("status") == "FAIL" or result.get("failures"):
        return "failed"
    coverage = result.get("coverage") or {}
    eligible = (
        result.get("status") == "PASS"
        and int(result.get("invalid", 0)) == 0
        and coverage.get("complete") is True
        and coverage.get("missing_dates") == []
        and coverage.get("missing_meals") == []
        and result.get("source_provenance_valid") is True
        and bool(institution_id)
        and result.get("menu_quality_valid") is True
        and result.get("source_completeness_valid", True) is True
        and all(int(result.get(key, 0)) == 0 for key in
                ("unresolved_formula_values", "excel_error_menu_items", "unresolved_non_menu_artifacts"))
        and all(not classify_menu_token(item.get("name", "")) and not classify_menu_token(item.get("raw_text", ""))
                for record in result.get("records", []) for item in record.get("menu_items", []))
        and not any(issue.get("code") in {"YEAR_INFERRED_FROM_PUBLICATION", "PERIOD_CONFLICT"}
                    for issue in result.get("document_issues", []))
    )
    return "ready" if eligible else "review"
