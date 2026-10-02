from __future__ import annotations

from collections import Counter
from pathlib import Path

from parsers.excel.menu_artifacts import CATEGORIES, classify_menu_token
from .validation import read_json


def scan_public_menus(root: Path) -> dict:
    counts = Counter()
    documents, slots, months, institutions = set(), set(), set(), set()
    occurrences = []
    files = list((root / "menus").rglob("*.json"))
    if not (root / "manifest.json").is_file():
        raise ValueError("menu lint requires a public manifest")
    for path in sorted(files):
        value = read_json(path)
        for day, meals in value["days"].items():
            for meal_type, slot in meals.items():
                for item in slot["menu_items"]:
                    category = classify_menu_token(item["name"]) or classify_menu_token(item["raw_text"])
                    if not category:
                        continue
                    counts[category] += 1
                    documents.update(slot["source_document_ids"])
                    slots.add((value["institution_id"], day, meal_type))
                    months.add(path.relative_to(root).as_posix())
                    institutions.add(value["institution_id"])
                    occurrences.append({"institution_id": value["institution_id"], "meal_date": day,
                                        "meal_type": meal_type, "classification": category,
                                        "name": item["name"], "source_document_ids": slot["source_document_ids"]})
    return {"status": "FAIL" if counts else "PASS", "month_files_scanned": len(files),
            "affected_docs": len(documents), "affected_slots": len(slots),
            "affected_month_files": len(months), "affected_institutions": len(institutions),
            "artifact_occurrences": sum(counts.values()),
            "artifact_counts": {category: counts[category] for category in CATEGORIES},
            "occurrences": occurrences}


def require_clean_public_menus(root: Path) -> dict:
    result = scan_public_menus(root)
    if result["status"] != "PASS":
        raise ValueError(f"public menu artifact lint failed: {result['artifact_counts']}")
    return {key: value for key, value in result.items() if key != "occurrences"}
