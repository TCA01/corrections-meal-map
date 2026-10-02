from __future__ import annotations

from collections import Counter
import calendar
from datetime import date

from .models import MealRecord, WorkbookGrid


def validate_records(
    records: list[MealRecord], workbook: WorkbookGrid, expected_year: int, expected_month: int,
    *, require_complete_month: bool = True,
) -> tuple[list[dict[str, str]], dict[str, object]]:
    document_issues: list[dict[str, str]] = []
    cell_index = {
        (sheet.name, cell.coordinate)
        for sheet in workbook.sheets
        for cell in sheet.cells
    }
    keys = Counter((record.meal_date, record.meal_type) for record in records)
    for record in records:
        issues: list[dict[str, str]] = []
        try:
            parsed = date.fromisoformat(record.meal_date)
        except ValueError:
            parsed = None
            issues.append({"code": "INVALID_DATE", "severity": "invalid"})
        if parsed and (parsed.year != expected_year or parsed.month != expected_month):
            issues.append({"code": "DATE_OUTSIDE_MEAL_MONTH", "severity": "warning"})
        source_weekday = record.source.get("source_weekday")
        if parsed and source_weekday is not None and parsed.weekday() != source_weekday:
            issues.append({"code": "WEEKDAY_MISMATCH", "severity": "invalid"})
        if keys[(record.meal_date, record.meal_type)] > 1:
            issues.append({"code": "DUPLICATE_DATE_MEAL", "severity": "invalid"})
        if not record.menu_items:
            issues.append({"code": "BLANK_MEAL", "severity": "invalid"})
        if record.source.get("menu_quality_unresolved"):
            issues.append({"code": "UNRESOLVED_MENU_SLOT", "severity": "invalid"})
        if not record.source.get("cells") or any(
            (record.source.get("sheet"), coordinate) not in cell_index
            for coordinate in record.source.get("cells", [])
        ):
            issues.append({"code": "INVALID_SOURCE_CELL", "severity": "invalid"})
        if not record.source.get("attachment_id"):
            issues.append({"code": "MISSING_INPUT_LINK", "severity": "invalid"})
        record.validation_issues = issues
        record.validation_status = (
            "invalid" if any(item["severity"] == "invalid" for item in issues)
            else "warning" if issues else "valid"
        )
    coverage = build_coverage_matrix(
        records, expected_year, expected_month, require_complete_month=require_complete_month
    )
    for missing_date in coverage["missing_dates"]:
        document_issues.append({
            "code": "MISSING_MEAL_DATE",
            "severity": "warning",
            "message": missing_date,
        })
    by_date: dict[str, set[str]] = {}
    for record in records:
        if record.menu_items and not record.source.get("menu_quality_unresolved"):
            by_date.setdefault(record.meal_date, set()).add(record.meal_type)
    for meal_date, meals in sorted(by_date.items()):
        missing = {"breakfast", "lunch", "dinner"} - meals
        if missing:
            document_issues.append({
                "code": "MISSING_DAILY_MEAL",
                "severity": "warning",
                "message": f"{meal_date}: missing {','.join(sorted(missing))}",
            })
    return document_issues, coverage


def build_coverage_matrix(
    records: list[MealRecord], year: int, month: int, *, require_complete_month: bool
) -> dict[str, object]:
    observed_slots = {(record.meal_date, record.meal_type) for record in records
                      if record.menu_items and not record.source.get("menu_quality_unresolved")}
    observed_dates = {meal_date for meal_date, _ in observed_slots}
    if require_complete_month:
        expected_dates = {
            date(year, month, day).isoformat()
            for day in range(1, calendar.monthrange(year, month)[1] + 1)
        }
    else:
        expected_dates = observed_dates
    meal_types = ("breakfast", "lunch", "dinner")
    missing_dates = sorted(expected_dates - observed_dates)
    missing_meals = [
        {"meal_date": meal_date, "meal_type": meal_type}
        for meal_date in sorted(expected_dates)
        for meal_type in meal_types
        if (meal_date, meal_type) not in observed_slots
    ]
    return {
        "coverage_scope": "full_month_daily_schedule" if require_complete_month else "observed_period_only",
        "expected_days": len(expected_dates),
        "observed_days": len(observed_dates & expected_dates),
        "expected_meal_slots": len(expected_dates) * len(meal_types),
        "observed_meal_slots": len(observed_slots),
        "missing_dates": missing_dates,
        "missing_meals": missing_meals,
        "complete": not missing_dates and not missing_meals,
    }
