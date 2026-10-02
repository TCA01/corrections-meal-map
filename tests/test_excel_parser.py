from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from parsers.excel.detector import UnsupportedExcelFormat, detect_excel_format
from parsers.excel.layout_analyzer import analyze_layout
from parsers.excel.meal_normalizer import normalize_date, normalize_meal_type, normalize_weekday, split_menu_text
from parsers.excel.models import CellData, MealRecord, SheetGrid, WorkbookGrid
from parsers.excel.pipeline import ExcelMealParser
from parsers.excel.validators import build_coverage_matrix, validate_records
from parsers.excel.workbook_reader import read_workbook


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "tests/fixtures/excel_samples/manifest.json").read_text(encoding="utf-8"))
EXCEL_SAMPLES = [item for item in MANIFEST if item["extension"] in {"xlsx", "xls"}]


def sample_path(index: int) -> Path:
    return ROOT / Path(*EXCEL_SAMPLES[index - 1]["local_path"].split("/"))


def test_actual_used_range_ignores_formatting_only_columns() -> None:
    workbook = read_workbook(sample_path(1), "xlsx")
    sheet = workbook.sheets[0]
    assert sheet.actual_max_col == 6
    assert sheet.actual_range == "A1:F37"


def test_merged_cell_reconstruction_preserves_parent_and_inherited_meaning() -> None:
    sheet = read_workbook(sample_path(1), "xlsx").sheets[0]
    assert sheet.cell(5, 1).merged_parent == "A4"
    assert sheet.effective_text(5, 1) == "일"


def test_xlsx_signature_detection() -> None:
    assert detect_excel_format(sample_path(1)) == "xlsx"


def test_genuine_xls_signature_detection() -> None:
    assert detect_excel_format(sample_path(4)) == "xls"


def test_xls_extension_with_xlsx_content_uses_xlsx_reader() -> None:
    workbook = read_workbook(sample_path(3), "xls")
    assert workbook.detected_format == "xlsx"
    assert workbook.format_extension_mismatch is True


def test_unsupported_signature_fails_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "bad.xls"
    path.write_bytes(b"not-an-excel-file")
    with pytest.raises(UnsupportedExcelFormat):
        detect_excel_format(path)


def test_excel_serial_date() -> None:
    assert normalize_date(45292, 2024, 1).isoformat() == "2024-01-01"


def test_datetime_cell() -> None:
    assert normalize_date(datetime(2026, 10, 3), 2026, 10).isoformat() == "2026-10-03"


def test_day_only_cell_uses_metadata_period() -> None:
    assert normalize_date(3, 2026, 10).isoformat() == "2026-10-03"


def test_nfkc_compatibility_ideograph_normalizes_to_friday() -> None:
    assert normalize_weekday("金") == 4


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("조 식", "breakfast"), ("점심식사", "lunch"), ("석식", "dinner")],
)
def test_meal_type_normalization(raw: str, expected: str) -> None:
    assert normalize_meal_type(raw) == expected


def test_menu_splitting_preserves_parenthesized_food_name() -> None:
    items = split_menu_text("구운김(2장) / 미역국\n배추김치")
    assert [item.name for item in items] == ["구운김(2장)", "미역국", "배추김치"]


def record(meal_date: str = "2026-10-03", meal_type: str = "breakfast") -> MealRecord:
    return MealRecord(
        institution_id="KR_CORR_TEST",
        meal_date=meal_date,
        meal_type=meal_type,
        menu_items=[],
        source={"attachment_id": "a", "sheet": "S", "cells": ["A1"], "source_weekday": None},
        parser={"format": "xlsx", "layout_family": "test", "parser_version": "3A.1", "confidence": "high"},
    )


def workbook() -> WorkbookGrid:
    return WorkbookGrid(
        "test.xlsx", "xlsx", "xlsx", False,
        [SheetGrid("S", 1, 1, 1, 1, [], [CellData("A1", 1, 1, "x", "x")])],
    )


def test_invalid_date_detection() -> None:
    item = record("2026-02-30")
    validate_records([item], workbook(), 2026, 2)
    assert item.validation_status == "invalid"
    assert item.validation_issues[0]["code"] == "INVALID_DATE"


def test_blank_meal_detection() -> None:
    item = record()
    validate_records([item], workbook(), 2026, 10)
    assert any(issue["code"] == "BLANK_MEAL" for issue in item.validation_issues)


def test_duplicate_date_meal_detection() -> None:
    first = record()
    second = deepcopy(first)
    first.menu_items = split_menu_text("밥")
    second.menu_items = split_menu_text("국")
    validate_records([first, second], workbook(), 2026, 10)
    assert all(any(issue["code"] == "DUPLICATE_DATE_MEAL" for issue in item.validation_issues) for item in (first, second))


def test_weekday_validation() -> None:
    item = record("2026-10-03")
    item.menu_items = split_menu_text("밥")
    item.source["source_weekday"] = 0
    validate_records([item], workbook(), 2026, 10)
    assert any(issue["code"] == "WEEKDAY_MISMATCH" for issue in item.validation_issues)


def test_missing_whole_date_is_reported_by_coverage_matrix() -> None:
    records = []
    for day in range(1, 32):
        if day == 6:
            continue
        for meal_type in ("breakfast", "lunch", "dinner"):
            item = record(f"2026-01-{day:02d}", meal_type)
            item.menu_items = split_menu_text("밥")
            records.append(item)
    coverage = build_coverage_matrix(records, 2026, 1, require_complete_month=True)
    assert coverage["missing_dates"] == ["2026-01-06"]
    assert coverage["observed_days"] == 30
    assert coverage["observed_meal_slots"] == 90


def test_complete_month_coverage_has_no_missing_slots() -> None:
    records = []
    for day in range(1, 29):
        for meal_type in ("breakfast", "lunch", "dinner"):
            item = record(f"2026-02-{day:02d}", meal_type)
            item.menu_items = split_menu_text("밥")
            records.append(item)
    coverage = build_coverage_matrix(records, 2026, 2, require_complete_month=True)
    assert coverage["complete"] is True
    assert coverage["expected_meal_slots"] == coverage["observed_meal_slots"] == 84


def test_layout_family_detection_for_date_rows() -> None:
    sheet = read_workbook(sample_path(1), "xlsx").sheets[0]
    assert analyze_layout(sheet).family == "date_rows_meal_columns"


def test_layout_family_detection_for_meal_rows() -> None:
    sheet = read_workbook(sample_path(12), "xlsx").sheets[0]
    assert analyze_layout(sheet).family == "meal_rows_weekday_columns"


def test_unsupported_layout_is_left_unresolved() -> None:
    sheet = SheetGrid("notes", 1, 1, 1, 1, [], [CellData("A1", 1, 1, "memo", "memo")])
    assert analyze_layout(sheet) is None


def test_source_provenance_is_present_in_actual_parse() -> None:
    result = ExcelMealParser(ROOT).parse_sample(EXCEL_SAMPLES[0])
    assert result["records"][0]["schema_version"] == "1.0"
    source = result["records"][0]["source"]
    assert source["post_id"] and source["attachment_id"] and source["sheet"] and source["cells"]


def test_false_pass_legacy_xls_has_all_fridays_and_full_coverage() -> None:
    sample = next(item for item in EXCEL_SAMPLES if item["post_id"] == "47472")
    result = ExcelMealParser(ROOT).parse_sample(sample)
    keys = {(item["meal_date"], item["meal_type"]) for item in result["records"]}
    for day in (6, 13, 20, 27):
        for meal_type in ("breakfast", "lunch", "dinner"):
            assert (f"2012-01-{day:02d}", meal_type) in keys
    assert result["records_generated"] == 93
    assert result["coverage"]["complete"] is True
    assert result["status"] == "PASS"


def test_existing_blank_cells_remain_partial_without_synthetic_menu() -> None:
    result = ExcelMealParser(ROOT).parse_sample(EXCEL_SAMPLES[0])
    assert result["status"] == "PARTIAL"
    assert result["coverage"]["missing_meals"]
    assert all(menu["name"] != "0" for item in result["records"] for menu in item["menu_items"])


def test_missing_all_three_meals_for_date_forces_partial() -> None:
    sample = next(item for item in EXCEL_SAMPLES if item["post_id"] == "71247")
    result = ExcelMealParser(ROOT).parse_sample(sample)
    assert result["coverage"]["missing_dates"] == ["2022-09-29", "2022-09-30"]
    assert result["status"] == "PARTIAL"
    assert result["production_eligible"] is False


def test_golden_excel_records_match_directly_verified_cells() -> None:
    fixture = json.loads(
        (ROOT / "tests/fixtures/golden_excel/expected.json").read_text(encoding="utf-8")
    )
    sample_map = {(item["post_id"], item["attachment_id"]): item for item in EXCEL_SAMPLES}
    parser = ExcelMealParser(ROOT)
    expected_count = exact = 0
    for document in fixture["documents"]:
        result = parser.parse_sample(sample_map[(document["post_id"], document["attachment_id"])])
        actual = {
            (item["meal_date"], item["meal_type"]): [menu["name"] for menu in item["menu_items"]]
            for item in result["records"]
        }
        for expected in document["expected"]:
            expected_count += 1
            key = (expected["meal_date"], expected["meal_type"])
            exact += actual.get(key) == expected["menu_items"]
    assert expected_count == 30
    assert exact == expected_count
