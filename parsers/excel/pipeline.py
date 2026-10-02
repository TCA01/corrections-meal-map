from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .detector import UnsupportedExcelFormat
from .layout_analyzer import select_candidate_sheets
from .models import ParseFailure
from .table_extractor import extract_records
from .validators import validate_records
from .workbook_reader import read_workbook
from .menu_quality import assess_menu_quality
from .menu_artifacts import CATEGORIES
from .completeness import source_coverage, suspicious_meals


class ExcelMealParser:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def parse_sample(self, sample: dict[str, Any], output_root: Path | None = None) -> dict[str, Any]:
        path = self.project_root / Path(*str(sample["local_path"]).split("/"))
        failures: list[ParseFailure] = []
        try:
            workbook = read_workbook(path, str(sample.get("extension") or ""))
        except (UnsupportedExcelFormat, OSError, ValueError) as error:
            return self._failed(sample, "CORRUPT_WORKBOOK", str(error))
        year, month, period_evidence, period_warnings = self._period(sample, workbook)
        if year is None or month is None:
            return self._failed(sample, "AMBIGUOUS_DATE", "year/month could not be resolved")
        candidates = select_candidate_sheets(workbook.sheets)
        if not candidates:
            return self._failed(sample, "UNSUPPORTED_LAYOUT", "no supported three-meal layout found")
        records = []
        profiles = []
        document_issues = list(period_warnings)
        quality_results = []
        completeness_results = []
        for sheet, profile in candidates:
            # A complete supplement schedule is not a complete daily meal.
            # This is source evidence, not a heuristic based on item count.
            title_text = ' '.join(cell.text for cell in sheet.cells if cell.row <= 6 and not cell.merged_parent)
            if any(word in sheet.name or word in title_text for word in ('직원', '교도관')):
                document_issues.append({'code':'STAFF_TABLE_SELECTED', 'severity':'warning',
                                        'message':'selected table explicitly identifies staff, not inmate meals'})
            if re.search(r'기존\s*식단.{0,40}추가', title_text):
                document_issues.append({'code':'SUPPLEMENTARY_ONLY_TABLE', 'severity':'warning',
                                        'message':'selected table explicitly adds to an existing meal; not a full meal list'})
            profiles.append({
                **profile.to_dict(),
                "institution_id": sample.get("institution_id"),
                "filename": sample.get("filename"),
            })
            extracted = extract_records(sheet, profile, sample, workbook.detected_format, year, month)
            quality_results.append(assess_menu_quality(extracted, sheet))
            breakfasts = [r for r in extracted if r.meal_type == 'breakfast']
            # Some juvenile supplement sheets omit their "existing meal +"
            # note. Context plus month-long dairy-only breakfasts is uncertain
            # source scope, NOT proof that a legitimate one-item meal is wrong.
            if ('소년수용자' in title_text.replace(' ', '') and len(breakfasts) >= 14
                    and all(len(r.menu_items) == 1 and r.menu_items[0].name in {'우유', '두유'}
                            for r in breakfasts)
                    and not re.search(r'기존\s*식단.{0,40}추가', title_text)):
                document_issues.append({'code':'SUPPLEMENTARY_SCOPE_UNCERTAIN', 'severity':'warning',
                                        'message':'juvenile table has month-long dairy-only breakfasts; full-meal scope needs review'})
            completeness_results.append(source_coverage(extracted, sheet))
            if not extracted:
                failures.append(ParseFailure("UNSUPPORTED_LAYOUT", "layout produced no records", sheet.name))
            records.extend(extracted)
        require_complete_month = bool(profiles) and all(
            profile.get("coverage_scope") == "full_month_daily_schedule" for profile in profiles
        )
        validation_issues, coverage = validate_records(
            records, workbook, year, month, require_complete_month=require_complete_month
        )
        document_issues.extend(validation_issues)
        document_issues.extend(issue for q in completeness_results for issue in q['issues'])
        if period_warnings:
            for record in records:
                record.validation_issues.extend(period_warnings)
                if record.validation_status != "invalid":
                    record.validation_status = "warning"
        quality = {
            "menu_quality_valid": all(q["menu_quality_valid"] for q in quality_results),
            **{key: sum(q[key] for q in quality_results) for key in
               ("resolved_formula_cells", "unresolved_formula_values", "excel_error_menu_items",
                "unresolved_non_menu_artifacts", "unresolved_slots", "excluded_artifacts")},
            "artifact_counts": {category: sum(q["artifact_counts"][category] for q in quality_results) for category in CATEGORIES},
        }
        semantic_issues = [issue for q in quality_results for issue in q["issues"]]
        document_issues.extend(issue for issue in semantic_issues if issue["severity"] != "info")
        invalid = sum(record.validation_status == "invalid" for record in records)
        warnings = sum(record.validation_status == "warning" for record in records)
        provenance_valid = all(
            not any(issue["code"] in {"INVALID_SOURCE_CELL", "MISSING_INPUT_LINK"} for issue in record.validation_issues)
            for record in records
        )
        if not records:
            status = "FAIL"
        elif failures or invalid or document_issues or not coverage["complete"] or not provenance_valid:
            status = "PARTIAL"
        else:
            status = "PASS"
        result = {
            "sample_id": f"{sample.get('post_id')}-{sample.get('attachment_id')}",
            "post_id": sample.get("post_id"),
            "attachment_id": sample.get("attachment_id"),
            "filename": sample.get("filename"),
            "institution_id": sample.get("institution_id"),
            "declared_extension": sample.get("extension"),
            "detected_format": workbook.detected_format,
            "format_extension_mismatch": workbook.format_extension_mismatch,
            "meal_year": year,
            "meal_month": month,
            "period_evidence": period_evidence,
            "layout_profiles": profiles,
            "status": status,
            "records_generated": len(records),
            "valid": sum(record.validation_status == "valid" for record in records),
            "warnings": warnings,
            "invalid": invalid,
            "unresolved": len(failures) + len(document_issues),
            "coverage": coverage,
            "source_provenance_valid": provenance_valid,
            "production_eligible": (
                status == "PASS" and invalid == 0
                and not coverage["missing_dates"] and provenance_valid and quality["menu_quality_valid"]
            ),
            "source_completeness_valid": all(q['source_completeness_valid'] for q in completeness_results),
            "completeness_candidates": suspicious_meals([r.to_dict() for r in records])['candidates'],
            **quality,
            "menu_quality_issues": semantic_issues,
            "menu_artifacts": [artifact for q in quality_results for artifact in q["artifacts"]],
            "document_issues": document_issues,
            "failures": [failure.to_dict() for failure in failures],
            "records": [record.to_dict() for record in records],
        }
        if output_root:
            output_root.mkdir(parents=True, exist_ok=True)
            raw_root = output_root.parent.parent / "excel_raw_tables"
            raw_root.mkdir(parents=True, exist_ok=True)
            self._write_json(raw_root / f"{result['sample_id']}.json", workbook.to_dict())
            self._write_json(output_root / f"{result['sample_id']}.json", result)
        return result

    def _period(self, sample: dict[str, Any], workbook: object) -> tuple[int | None, int | None, list[str], list[dict[str, str]]]:
        year = _integer(sample.get("meal_year"))
        month = _integer(sample.get("meal_month"))
        evidence = []
        warnings = []
        if year and month:
            evidence.append("historical metadata year/month")
        # Period evidence is only trusted in title/header rows. Date-formatted
        # numeric costing cells deeper in a sheet can render as plausible but
        # unrelated calendar dates.
        texts = [
            cell.text for sheet in workbook.sheets for cell in sheet.cells
            if cell.text and cell.row <= 4
        ]
        explicit = []
        for text in texts[:500]:
            for match in re.finditer(r"(20\d{2})\s*년?\s*[./-]?\s*(1[0-2]|0?[1-9])\s*월?", text):
                candidate = (int(match.group(1)), int(match.group(2)))
                if 2010 <= candidate[0] <= 2035:
                    explicit.append(candidate)
            if isinstance(text, str) and re.fullmatch(r"20\d{2}-\d{2}-\d{2}(?:T.*)?", text):
                parsed = date.fromisoformat(text[:10])
                explicit.append((parsed.year, parsed.month))
        if (not year or not month) and explicit:
            year, month = Counter(explicit).most_common(1)[0][0]
            evidence.append("workbook cell year/month")
        filename = str(sample.get("filename") or "")
        if not month:
            match = re.search(r"(?<!\d)(1[0-2]|0?[1-9])\s*월", filename)
            if match:
                month = int(match.group(1))
                evidence.append("filename month")
        if not year:
            published = str(sample.get("published_date") or "")
            if re.match(r"20\d{2}", published):
                year = int(published[:4])
                evidence.append("publication year")
                warnings.append({
                    "code": "YEAR_INFERRED_FROM_PUBLICATION",
                    "severity": "warning",
                    "message": "meal year absent; publication year used",
                })
        if year and month and explicit and (year, month) not in explicit:
            warnings.append({
                "code": "PERIOD_CONFLICT",
                "severity": "warning",
                "message": f"metadata {year}-{month:02d} conflicts with workbook {explicit[0][0]}-{explicit[0][1]:02d}",
            })
        # Production manifests retain whether the collector filled in a missing
        # title year from publication. Do not let that fallback look explicit.
        metadata = sample.get("period_metadata") or {}
        if sample.get("metadata_year_inferred"):
            filename_year = _integer(metadata.get("filename_year"))
            filename_month = _integer(metadata.get("filename_month"))
            confirmed = (year, month) in explicit or (filename_year, filename_month) == (year, month)
            if confirmed:
                evidence.append("publication fallback confirmed by workbook/filename year/month")
            elif not any(issue["code"] == "YEAR_INFERRED_FROM_PUBLICATION" for issue in warnings):
                evidence.append("historical metadata publication-year fallback; not independently confirmed")
                warnings.append({
                    "code": "YEAR_INFERRED_FROM_PUBLICATION", "severity": "warning",
                    "message": "historical title lacks year; publication fallback not confirmed in workbook/filename",
                })
        return year, month, evidence, warnings

    @staticmethod
    def _failed(sample: dict[str, Any], code: str, message: str) -> dict[str, Any]:
        return {
            "sample_id": f"{sample.get('post_id')}-{sample.get('attachment_id')}",
            "post_id": sample.get("post_id"),
            "attachment_id": sample.get("attachment_id"),
            "filename": sample.get("filename"),
            "institution_id": sample.get("institution_id"),
            "declared_extension": sample.get("extension"),
            "detected_format": None,
            "format_extension_mismatch": False,
            "layout_profiles": [],
            "status": "FAIL",
            "records_generated": 0,
            "valid": 0,
            "warnings": 0,
            "invalid": 0,
            "unresolved": 1,
            "document_issues": [],
            "failures": [{"code": code, "message": message, "sheet": None}],
            "records": [],
        }

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
        temporary.replace(path)


def _integer(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)
