"""Audit-first cleanup. Unrecoverable values quarantine a document, not guess food."""
from __future__ import annotations

from collections import Counter

from .menu_artifacts import CATEGORIES, ISSUE_CODES, classify_menu_token
from .meal_normalizer import split_menu_tokens
from .models import MealRecord, SheetGrid


def assess_menu_quality(records: list[MealRecord], sheet: SheetGrid) -> dict:
    by_coordinate = {cell.coordinate: cell for cell in sheet.cells}
    artifacts = []
    issues = []
    resolved, unresolved = set(), set()
    unsafe_slots = set()
    error_items = 0
    unresolved_artifacts = 0
    for record in records:
        origins = {}
        error_tokens = set()
        formulas = []
        for coordinate in record.source["cells"]:
            cell = by_coordinate[coordinate]
            for token in split_menu_tokens(cell.text):
                origins.setdefault(token, coordinate)
                if cell.is_excel_error:
                    error_tokens.add(token)
            if cell.is_formula:
                formulas.append({"source_cell": coordinate, "formula": cell.formula or str(cell.raw_value),
                                 "display_text": cell.text, "cache_status": cell.formula_cache_status})
                (resolved if cell.formula_cache_status == "resolved" else unresolved).add(coordinate)
        if formulas:
            record.source["formula_cells"] = formulas
        classifications = ["excel_error" if item.name in error_tokens else classify_menu_token(item.name)
                           for item in record.menu_items]
        clean = [item for item, category in zip(record.menu_items, classifications) if category is None]
        # Metadata can only be removed safely when it is a trailing suffix.
        # Errors/unresolved formula values always threaten menu completeness.
        first_artifact = next((i for i, category in enumerate(classifications) if category), len(classifications))
        unsafe = (not clean or any(category in {"formula_literal", "excel_error"} for category in classifications)
                  or any(category is None for category in classifications[first_artifact:]))
        for item, category in zip(record.menu_items, classifications):
            if category is None:
                continue
            artifact = {"sheet": sheet.name, "source_cell": origins.get(item.raw_text),
                        "meal_date": record.meal_date, "meal_type": record.meal_type,
                        "raw_text": item.raw_text, "source_raw_text": record.source["raw_text"],
                        "classification": category, "action": "quarantined" if unsafe else "excluded_from_menu"}
            artifacts.append(artifact)
            issues.append({"code": ISSUE_CODES[category], "severity": "warning" if unsafe else "info",
                           "meal_date": record.meal_date, "meal_type": record.meal_type,
                           "source_cell": artifact["source_cell"], "action": artifact["action"]})
            error_items += category == "excel_error"
            unresolved_artifacts += unsafe and category not in {"excel_error", "formula_literal"}
        if unsafe and any(classifications):
            unsafe_slots.add((record.meal_date, record.meal_type))
            record.source["menu_quality_unresolved"] = True
        # An unresolved cached formula is unsafe even if the displayed error was
        # outside the exact classifier vocabulary.
        if any(f["cache_status"] != "resolved" for f in formulas):
            unsafe_slots.add((record.meal_date, record.meal_type))
            record.source["menu_quality_unresolved"] = True
        record.menu_items = clean
    counts = Counter(a["classification"] for a in artifacts)
    return {"artifacts": artifacts, "issues": issues, "resolved_formula_cells": len(resolved),
            "unresolved_formula_values": len(unresolved), "excel_error_menu_items": error_items,
            "unresolved_non_menu_artifacts": unresolved_artifacts, "unresolved_slots": len(unsafe_slots),
            "artifact_counts": {category: counts[category] for category in CATEGORIES},
            "excluded_artifacts": sum(a["action"] == "excluded_from_menu" for a in artifacts),
            "menu_quality_valid": not unsafe_slots}
