from __future__ import annotations

from dataclasses import dataclass

from .meal_normalizer import days_in_text, normalize_meal_type, normalize_weekday
from .models import SheetGrid
from openpyxl.utils.cell import range_boundaries
from .menu_artifacts import classify_menu_token


def table_body_end(sheet: SheetGrid, header_row: int, first_meal_column: int) -> int:
    """A footer spanning label AND meal columns ends the table (incl. snacks)."""
    bottom = sheet.actual_max_row or header_row
    for cell in sheet.cells:
        if cell.row <= header_row or cell.column >= first_meal_column or not cell.text or cell.merged_parent:
            continue
        if cell.merged_range:
            left, top, right, end = range_boundaries(cell.merged_range)
            if right >= first_meal_column:
                bottom = min(bottom, cell.row - 1)
        if classify_menu_token(cell.text) in {'instruction_note', 'cost_metadata'}:
            bottom = min(bottom, cell.row - 1)
    return bottom


@dataclass(frozen=True)
class LayoutProfile:
    family: str
    confidence: str
    evidence: list[str]
    sheet: str
    header_cells: dict[str, str]
    coverage_scope: str = "full_month_daily_schedule"

    def to_dict(self) -> dict[str, object]:
        return {
            "detected_layout_family": self.family,
            "confidence": self.confidence,
            "detection_evidence": self.evidence,
            "sheet": self.sheet,
            "header_cells": self.header_cells,
            "coverage_scope": self.coverage_scope,
        }


def analyze_layout(sheet: SheetGrid) -> LayoutProfile | None:
    cells = [cell for cell in sheet.cells if cell.text and not cell.merged_parent]
    meal_headers = [(cell, normalize_meal_type(cell.text)) for cell in cells]
    meal_headers = [(cell, meal) for cell, meal in meal_headers if meal]
    best_row = None
    for row in sorted({cell.row for cell, _ in meal_headers}):
        row_headers = [(cell, meal) for cell, meal in meal_headers if cell.row == row]
        if {meal for _, meal in row_headers} == {"breakfast", "lunch", "dinner"}:
            best_row = row_headers
            break
    if best_row:
        header_row = best_row[0][0].row
        first_meal_col = min(cell.column for cell, _ in best_row)
        body_end = table_body_end(sheet, header_row, first_meal_col)
        day_count = sum(
            bool(days_in_text(cell.raw_value))
            for cell in cells
            if header_row < cell.row <= body_end and cell.column < first_meal_col and not cell.is_formula
        )
        weekday_count = sum(
            normalize_weekday(cell.text) is not None
            for cell in cells
            if header_row < cell.row <= body_end and cell.column < first_meal_col
        )
        weekday_anchors = [cell for cell in cells if header_row < cell.row <= body_end
                           and cell.column < first_meal_col
                           and normalize_weekday(cell.text) is not None]
        # Dates often run DOWN a weekly menu block, or occur only on its last
        # row. Counting dates alone confused these with one-day-per-row tables.
        weekly = (5 <= len(weekday_anchors) <= 7
                  and len({normalize_weekday(c.text) for c in weekday_anchors}) >= 5
                  and max(c.row for c in weekday_anchors) - min(c.row for c in weekday_anchors) > 7)
        family = "date_rows_meal_columns" if day_count >= 5 and not weekly else "weekday_blocks_meal_columns"
        evidence = [
            f"three meal headers share row {header_row}",
            f"{day_count} day-number cells before meal columns",
            f"{weekday_count} weekday anchors before meal columns",
        ]
        return LayoutProfile(
            family=family,
            confidence="high" if day_count >= 5 or weekday_count >= 5 else "medium",
            evidence=evidence,
            sheet=sheet.name,
            header_cells={meal: cell.coordinate for cell, meal in best_row},
        )
    by_column: dict[int, list[tuple[object, str]]] = {}
    for cell, meal in meal_headers:
        by_column.setdefault(cell.column, []).append((cell, meal))
    for column, headers in by_column.items():
        if {meal for _, meal in headers} == {"breakfast", "lunch", "dinner"}:
            weekday_headers = [
                cell for cell in cells
                if cell.column > column and normalize_weekday(cell.text) is not None
            ]
            if len({cell.column for cell in weekday_headers}) >= 5:
                return LayoutProfile(
                    family="meal_rows_weekday_columns",
                    confidence="high",
                    evidence=[
                        f"meal labels aligned in column {column}",
                        f"{len({cell.column for cell in weekday_headers})} weekday columns",
                    ],
                    sheet=sheet.name,
                    header_cells={meal: cell.coordinate for cell, meal in headers},
                )
    return None


def select_candidate_sheets(sheets: list[SheetGrid]) -> list[tuple[SheetGrid, LayoutProfile]]:
    candidates = []
    for sheet in sheets:
        profile = analyze_layout(sheet)
        if profile:
            candidates.append((sheet, profile))
    inmate = [item for item in candidates if "수용자" in item[0].name and "직원" not in item[0].name]
    if inmate:
        return [inmate[0]]
    non_staff = [item for item in candidates if not any(word in item[0].name for word in ("직원", "교도관"))]
    # The representative workbooks use the first matching sheet as the
    # publishable table; later matching sheets are costing/detail variants.
    return [(non_staff or candidates)[0]] if candidates else []
