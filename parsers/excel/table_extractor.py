from __future__ import annotations

from datetime import date
from typing import Any

from openpyxl.utils.cell import coordinate_from_string, column_index_from_string

from .layout_analyzer import LayoutProfile
from .meal_normalizer import (
    combine_menu_cells,
    dates_for_weekday,
    days_in_text,
    normalize_weekday,
)
from .models import CellData, MealRecord, SheetGrid
from .menu_artifacts import classify_menu_token


def _column(coordinate: str) -> int:
    return column_index_from_string(coordinate_from_string(coordinate)[0])


def _header_columns(profile: LayoutProfile) -> dict[str, int]:
    return {meal: _column(coordinate) for meal, coordinate in profile.header_cells.items()}


def _record(
    sample: dict[str, Any], detected_format: str, profile: LayoutProfile,
    meal_date: date, meal_type: str, values: list[tuple[str, str]], confidence: str,
    source_weekday: int | None = None,
) -> MealRecord | None:
    items, raw_text = combine_menu_cells(value for _, value in values)
    if not items:
        return None
    return MealRecord(
        institution_id=str(sample.get("institution_id") or ""),
        meal_date=meal_date.isoformat(),
        meal_type=meal_type,
        menu_items=items,
        source={
            "post_id": str(sample.get("post_id") or ""),
            "attachment_id": str(sample.get("attachment_id") or ""),
            "filename": str(sample.get("filename") or ""),
            "sheet": profile.sheet,
            "cells": [coordinate for coordinate, _ in values],
            "raw_text": raw_text,
            "meal_label": meal_type,
            "source_weekday": source_weekday,
        },
        parser={
            "format": detected_format,
            "layout_family": profile.family,
            "parser_version": "3B.2",
            "confidence": confidence,
        },
    )


def extract_records(
    sheet: SheetGrid, profile: LayoutProfile, sample: dict[str, Any],
    detected_format: str, year: int, month: int,
) -> list[MealRecord]:
    if profile.family == "date_rows_meal_columns":
        return _date_rows(sheet, profile, sample, detected_format, year, month)
    if profile.family == "weekday_blocks_meal_columns":
        return _weekday_blocks(sheet, profile, sample, detected_format, year, month)
    if profile.family == "meal_rows_weekday_columns":
        return _meal_rows(sheet, profile, sample, detected_format, year, month)
    return []


def _date_rows(
    sheet: SheetGrid, profile: LayoutProfile, sample: dict[str, Any],
    detected_format: str, year: int, month: int,
) -> list[MealRecord]:
    columns = _header_columns(profile)
    header_row = min(
        cell.row for cell in sheet.cells if cell.coordinate in profile.header_cells.values()
    )
    first_meal = min(columns.values())
    candidate_columns = range(sheet.actual_min_col or 1, first_meal)
    day_column = max(
        candidate_columns,
        key=lambda column: sum(
            bool(days_in_text(cell.raw_value))
            for cell in sheet.cells
            if cell.column == column and cell.row > header_row
        ),
    )
    cell_map = sheet.by_position()
    coordinate_map = {cell.coordinate: cell for cell in sheet.cells}
    records: list[MealRecord] = []
    for row in range(header_row + 1, (sheet.actual_max_row or header_row) + 1):
        day_cell = cell_map.get((row, day_column))
        if not day_cell:
            continue
        days = days_in_text(day_cell.raw_value)
        if not days:
            continue
        weekday = None
        for column in range(day_column - 1, 0, -1):
            candidate = cell_map.get((row, column))
            value = candidate.text if candidate else ""
            if candidate and not value and candidate.merged_parent:
                parent = coordinate_map.get(candidate.merged_parent)
                value = parent.text if parent else ""
            weekday = normalize_weekday(value)
            if weekday is not None:
                break
        for day in days:
            try:
                meal_date = date(year, month, day)
            except ValueError:
                continue
            for meal_type, column in columns.items():
                cell = cell_map.get((row, column))
                if not cell:
                    continue
                record = _record(
                    sample, detected_format, profile, meal_date, meal_type,
                    [(cell.coordinate, cell.text)], "high", weekday,
                )
                if record:
                    records.append(record)
    return records


def _weekday_blocks(
    sheet: SheetGrid, profile: LayoutProfile, sample: dict[str, Any],
    detected_format: str, year: int, month: int,
) -> list[MealRecord]:
    columns = _header_columns(profile)
    # WorkbookGrid is read-only during extraction. Build the lookup once even
    # for wide costing sheets, instead of rebuilding it for every cell query.
    cell_map = sheet.by_position()
    header_row = min(
        cell.row for cell in sheet.cells if cell.coordinate in profile.header_cells.values()
    )
    first_meal = min(columns.values())
    anchors: list[tuple[int, int]] = []
    for row in range(header_row + 1, (sheet.actual_max_row or header_row) + 1):
        weekday = None
        for column in range(1, first_meal):
            cell = cell_map.get((row, column))
            if cell is None or cell.merged_parent:
                continue
            weekday = normalize_weekday(cell.text)
            if weekday is not None:
                break
        if weekday is not None and (not anchors or anchors[-1][0] != row):
            anchors.append((row, weekday))
    header_words = {
        "식단명", "품명", "가격", "금액", "중량", "수량",
        "아침", "점심", "저녁", "조식", "중식", "석식",
    }
    first_anchor = anchors[0][0] if anchors else header_row + 1
    previous_values = [
        cell.text.strip().replace(" ", "")
        for column in columns.values()
        if (cell := cell_map.get((first_anchor - 1, column))) is not None
        and _menu_candidate(cell, primary=True)
    ]
    shift_all = bool(previous_values) and not all(value in header_words for value in previous_values)
    block_starts = []
    for anchor_row, weekday in anchors:
        start_row = anchor_row - 1 if shift_all and anchor_row - 1 > header_row else anchor_row
        block_starts.append((start_row, weekday))
    records: list[MealRecord] = []
    ordered = sorted(columns.items(), key=lambda item: item[1])
    for index, (start_row, weekday) in enumerate(block_starts):
        end_row = block_starts[index + 1][0] - 1 if index + 1 < len(block_starts) else min(
            sheet.actual_max_row or start_row, start_row + 8
        )
        for meal_index, (meal_type, start_column) in enumerate(ordered):
            end_column = ordered[meal_index + 1][1] - 1 if meal_index + 1 < len(ordered) else start_column
            values = []
            for row in range(start_row, end_row + 1):
                for column in range(start_column, end_column + 1):
                    cell = cell_map.get((row, column))
                    if cell and _menu_candidate(cell, primary=column == start_column):
                        values.append((cell.coordinate, cell.text))
            for meal_date in dates_for_weekday(year, month, weekday):
                record = _record(
                    sample, detected_format, profile, meal_date, meal_type, values, "medium", weekday
                )
                if record:
                    records.append(record)
    return records


def _meal_rows(
    sheet: SheetGrid, profile: LayoutProfile, sample: dict[str, Any],
    detected_format: str, year: int, month: int,
) -> list[MealRecord]:
    cell_map = sheet.by_position()
    meal_rows = {
        meal: next(cell.row for cell in sheet.cells if cell.coordinate == coordinate)
        for meal, coordinate in profile.header_cells.items()
    }
    first_meal_column = min(
        next(cell.column for cell in sheet.cells if cell.coordinate == coordinate)
        for coordinate in profile.header_cells.values()
    )
    weekday_columns: dict[int, int] = {}
    for cell in sheet.cells:
        weekday = normalize_weekday(cell.text)
        if weekday is not None and cell.column > first_meal_column:
            weekday_columns[cell.column] = weekday
    ordered_rows = sorted(meal_rows.items(), key=lambda item: item[1])
    records: list[MealRecord] = []
    for meal_index, (meal_type, start_row) in enumerate(ordered_rows):
        end_row = ordered_rows[meal_index + 1][1] - 1 if meal_index + 1 < len(ordered_rows) else min(
            sheet.actual_max_row or start_row, start_row + 6
        )
        for column, weekday in weekday_columns.items():
            values = []
            for row in range(start_row, end_row + 1):
                cell = cell_map.get((row, column))
                if cell and _menu_candidate(cell, primary=True):
                    values.append((cell.coordinate, cell.text))
            for meal_date in dates_for_weekday(year, month, weekday):
                record = _record(
                    sample, detected_format, profile, meal_date, meal_type, values, "medium", weekday
                )
                if record:
                    records.append(record)
    return records


def _numeric_text(value: str) -> bool:
    try:
        float(value.replace(",", ""))
        return True
    except ValueError:
        return False


def _menu_candidate(cell: CellData, *, primary: bool) -> bool:
    if not cell.text:
        return False
    if cell.is_formula and cell.formula_cache_status != "resolved":
        # Adjacent quantity/price formula columns are not menu columns. In a
        # menu column, an unresolved formula must be audited, not skipped.
        return primary
    if _numeric_text(cell.text):
        return primary and classify_menu_token(cell.text) == "placeholder"
    return True
