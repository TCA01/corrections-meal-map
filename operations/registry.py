from __future__ import annotations

import re
import zipfile

from parsers.excel import ExcelMealParser
from parsers.excel.detector import OLE_SIGNATURE
from parsers.excel.workbook_reader import read_workbook
from parsers.excel.layout_analyzer import analyze_layout
from production.gate import production_route
from production.io import verified_file
from production.validation import KNOWN_LAYOUTS, validate_record, validate_public_source
from production.pipeline import ProductionExcelPipeline


def detect_format(path):
    with path.open("rb") as handle:
        signature = handle.read(1024)
    if signature.startswith(b"%PDF-"):
        return "pdf"
    if signature.startswith(OLE_SIGNATURE):
        # HWP v5 is an OLE container too; distinguish its stream names.
        import olefile
        with olefile.OleFileIO(path) as ole:
            streams = {"/".join(name) for name in ole.listdir()}
        if "FileHeader" in streams and any(n.startswith("BodyText/") for n in streams):
            return "hwp"
        return "xls" if streams & {"Workbook", "Book"} else "unknown"
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
        if {"xl/workbook.xml", "[Content_Types].xml"} <= names:
            return "xlsx"
        if "Contents/content.hpf" in names or "Contents/section0.xml" in names:
            return "hwpx"
    return "unknown"


class ParserRegistry:
    """Handlers return route/result/reasons; registering a parser needs no core change."""
    def __init__(self, root):
        self.root = root
        self.excel = ExcelMealParser(root)
        self.handlers = {"xlsx": self._excel, "xls": self._excel}

    def register(self, format_name, handler):
        self.handlers[format_name] = handler

    def process(self, item):
        if not verified_file(self.root, item):
            return "failed", {}, ["VALIDATION_FAILED"]
        try:
            item["detected_format"] = detect_format(self.root / item["local_path"])
            handler = self.handlers.get(item["detected_format"])
            if handler is None:
                if item["detected_format"] == "unknown":
                    return "failed", {}, ["VALIDATION_FAILED"]
                return "unsupported", {"status": "UNSUPPORTED_FOR_PRODUCTION"}, ["UNSUPPORTED_FORMAT"]
            return handler(item)
        except Exception as error:
            # Private diagnostics may be retained separately; never expose paths/tracebacks in health.
            return "failed", {"error_type": type(error).__name__}, ["VALIDATION_FAILED"]

    def _excel(self, item):
        result = self.excel.parse_sample(item)
        codes = {v.get("code", "") for v in result.get("failures", []) + result.get("document_issues", [])}
        families = {p.get("detected_layout_family") for p in result.get("layout_profiles", [])}
        if "UNSUPPORTED_LAYOUT" in codes or families - KNOWN_LAYOUTS:
            result["layout_diagnostics"] = self.diagnose(item)
            return "review", result, ["NEW_LAYOUT"]
        item["layout_family"] = sorted(families)[0] if families else None
        route = production_route(result, institution_id=item.get("institution_id"))
        if route == "ready":
            try:
                validate_public_source(ProductionExcelPipeline._public_source(item))
                if not result.get("records"):
                    raise ValueError("empty READY")
                for record in result["records"]:
                    validate_record(record, institution_id=item["institution_id"])
            except (ValueError, KeyError, TypeError):
                return "review", result, ["VALIDATION_FAILED"]
            return "ready", result, []
        reasons = []
        coverage = result.get("coverage", {})
        if coverage.get("missing_dates") or "AMBIGUOUS_DATE" in codes:
            reasons.append("MISSING_DATE")
        if coverage.get("missing_meals"):
            reasons.append("MISSING_MEAL")
        for key, reason in [("unresolved_formula_values", "UNRESOLVED_FORMULA"),
                            ("excel_error_menu_items", "EXCEL_ERROR"),
                            ("unresolved_non_menu_artifacts", "MENU_ARTIFACT")]:
            if result.get(key):
                reasons.append(reason)
        return route, result, reasons or ["VALIDATION_FAILED"]

    def diagnose(self, item):
        workbook = read_workbook(self.root / item["local_path"], item["declared_extension"])
        sheets = []
        for sheet in workbook.sheets:
            texts = [cell.text for cell in sheet.cells if cell.text]
            profile = analyze_layout(sheet)
            sheets.append({"sheet": sheet.name, "actual_range": sheet.actual_range,
                           "merged_cell_count": len(sheet.merged_ranges),
                           "meal_keywords": sorted({word for word in ("조식", "중식", "석식", "아침", "점심", "저녁")
                                                    if any(word in text for text in texts)}),
                           "date_like_patterns": [text[:100] for text in texts
                                                  if re.search(r"\d{1,4}[./-]\d{1,2}|\d{1,2}일", text)][:20],
                           "closest_layout_family": profile.family if profile else None})
        return {"institution": item.get("institution_id"), "post_id": item["post_id"],
                "filename": item["filename"], "detected_format": item["detected_format"],
                "sheets": sheets, "source_url": item["post_url"]}
