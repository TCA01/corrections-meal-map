from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsers.excel import ExcelMealParser


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    manifest = json.loads((ROOT / "data/audit/parser_samples.json").read_text(encoding="utf-8"))
    samples = [item for item in manifest if item.get("extension") in {"xlsx", "xls"}]
    parser = ExcelMealParser(ROOT)
    sample_output = ROOT / "data/processed/samples/excel"
    results = []
    for sample in samples:
        try:
            result = parser.parse_sample(sample, sample_output)
        except Exception as error:  # keep the other representative files running
            result = parser._failed(sample, "PARSER_EXCEPTION", f"{type(error).__name__}: {error}")
        results.append(result)
        print(
            f"{result['status']:7} {str(result.get('detected_format') or '?'):4} "
            f"{result['records_generated']:4} {result['filename']}"
        )
    profiles = [
        {"sample_id": result["sample_id"], **profile}
        for result in results for profile in result.get("layout_profiles", [])
    ]
    record_statuses = Counter(
        record["validation_status"]
        for result in results for record in result.get("records", [])
    )
    summary = {
        "total_documents": len(results),
        "document_results": dict(Counter(result["status"] for result in results)),
        "format_results": {
            extension: dict(Counter(
                result["status"] for result in results
                if result.get("declared_extension") == extension
            ))
            for extension in ("xlsx", "xls")
        },
        "meal_records": {
            "total": sum(record_statuses.values()),
            "valid": record_statuses["valid"],
            "warning": record_statuses["warning"],
            "invalid": record_statuses["invalid"],
        },
        "failure_codes": dict(Counter(
            failure["code"] for result in results for failure in result.get("failures", [])
        )),
        "production_gate": {
            "eligible": sum(bool(result.get("production_eligible")) for result in results),
            "review_required": sum(not bool(result.get("production_eligible")) for result in results),
        },
    }
    golden_path = ROOT / "tests/fixtures/golden_excel/expected.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    result_map = {(str(item["post_id"]), str(item["attachment_id"])): item for item in results}
    comparisons = []
    coverage_comparisons = []
    exact = mismatch = 0
    coverage_statuses = Counter()
    for document in golden["documents"]:
        result = result_map[(document["post_id"], document["attachment_id"])]
        actual = {
            (record["meal_date"], record["meal_type"]): [menu["name"] for menu in record["menu_items"]]
            for record in result["records"]
        }
        for expected in document["expected"]:
            key = (expected["meal_date"], expected["meal_type"])
            matches = actual.get(key) == expected["menu_items"]
            exact += int(matches)
            mismatch += int(not matches)
            comparisons.append({
                "post_id": document["post_id"],
                "attachment_id": document["attachment_id"],
                **expected,
                "actual_menu_items": actual.get(key),
                "exact_match": matches,
            })
        expected_coverage = document["expected_coverage"]
        actual_coverage = result["coverage"]
        coverage_status = (
            "full" if actual_coverage["complete"]
            and actual_coverage["expected_days"] == expected_coverage["expected_days"]
            and actual_coverage["expected_meal_slots"] == expected_coverage["expected_meal_slots"]
            else "failed" if actual_coverage["observed_days"] == 0
            else "partial"
        )
        coverage_statuses[coverage_status] += 1
        coverage_comparisons.append({
            "post_id": document["post_id"],
            "attachment_id": document["attachment_id"],
            "status": coverage_status,
            "expected": expected_coverage,
            "actual": actual_coverage,
        })
    golden_report = {
        "menu_validation": {
            "golden_documents": len(golden["documents"]),
            "expected_meal_records": exact + mismatch,
            "exact_match": exact,
            "mismatch": mismatch,
            "accuracy_percent": round(exact * 100 / (exact + mismatch), 2) if exact + mismatch else 0,
            "comparisons": comparisons,
        },
        "coverage_validation": {
            "golden_documents": len(golden["documents"]),
            "full_coverage": coverage_statuses["full"],
            "partial_coverage": coverage_statuses["partial"],
            "failed_coverage": coverage_statuses["failed"],
            "comparisons": coverage_comparisons,
        },
    }
    compact_results = [{key: value for key, value in result.items() if key != "records"} for result in results]
    write_json(ROOT / "data/processed/excel_sample_results.json", compact_results)
    write_json(ROOT / "data/processed/excel_validation_report.json", summary)
    write_json(ROOT / "data/processed/excel_layout_profiles.json", profiles)
    write_json(ROOT / "data/processed/excel_golden_validation.json", golden_report)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    console_golden = {
        "menu_validation": {key: value for key, value in golden_report["menu_validation"].items() if key != "comparisons"},
        "coverage_validation": {key: value for key, value in golden_report["coverage_validation"].items() if key != "comparisons"},
    }
    print(json.dumps(console_golden, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
