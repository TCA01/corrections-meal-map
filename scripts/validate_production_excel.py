from __future__ import annotations

import json
import sys
import argparse
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from institutions.master import InstitutionMaster
from production.io import read_jsonl, verified_file, atomic_json
from production.validation import read_json, validate_dataset
from production.menu_lint import scan_public_menus
from parsers.excel.detector import detect_excel_format, UnsupportedExcelFormat
from openpyxl.styles.stylesheet import Stylesheet


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Validate the active production run without changing its data")
    parser.add_argument("--output", type=Path, help="optionally save verification evidence as a separate JSON")
    args = parser.parse_args()
    settings = Settings()
    current = read_json(settings.production_root / "current.json")
    root = (settings.production_root / current["run_path"]).resolve()
    if not root.is_relative_to((settings.production_root / "runs").resolve()):
        raise ValueError("current run is outside production/runs")
    report = read_json(root / "reports/excel_production_report.json")
    if current["dataset_version"] != report["run_metadata"]["dataset_version"]:
        raise ValueError("current pointer/report version mismatch")
    master = InstitutionMaster.load(settings.institutions_path)
    result = validate_dataset(root, report, {i.institution_id for i in master.institutions})
    lint = scan_public_menus(root / "web_data")
    result["menu_lint"] = {key: value for key, value in lint.items() if key != "occurrences"}
    manifest = read_jsonl(root / "excel_manifest.jsonl")
    downloaded = [i for i in manifest if i.get("download_status") in {"downloaded", "reused", "deduplicated"}]
    failures = [i["document_id"] for i in downloaded if not verified_file(settings.project_root, i)]
    signatures = Counter()
    mismatches = []
    unsupported = []
    for item in downloaded:
        try:
            detected = detect_excel_format(settings.project_root / item["local_path"])
            signatures[detected] += 1
            if detected != item["declared_extension"]:
                mismatches.append(item["document_id"])
        except (UnsupportedExcelFormat, OSError, ValueError):
            signatures["unsupported"] += 1
            unsupported.append(item["document_id"])
    result.update(raw_files_checked=len(downloaded), raw_integrity_failures=failures,
                  dataset_version=current["dataset_version"])
    result.update(format_signatures=dict(signatures), extension_mismatch_documents=mismatches,
                  unsupported_signature_documents=unsupported)
    parsed = [read_json(path) for path in (root / "parsed").glob("*.json")]
    result["record_validation_issues"] = dict(Counter(
        issue["code"] for document in parsed for record in document.get("records", [])
        for issue in record.get("validation_issues", [])
    ))
    result["parser_exception_types"] = dict(Counter(
        failure["message"].split(":", 1)[0] for document in parsed
        for failure in document.get("failures", []) if failure["code"] == "PARSER_EXCEPTION"
    ))
    # Read-only diagnosis of OOXML style references, without repairing originals.
    by_id = {item["document_id"]: item for item in manifest}
    style_failures = []
    alternate_styles = []
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    for document in parsed:
        if not any(f.get("message", "").startswith("IndexError:") for f in document.get("failures", [])):
            continue
        item = by_id[document["sample_id"]]
        path = settings.project_root / item["local_path"]
        if not zipfile.is_zipfile(path):
            continue
        with zipfile.ZipFile(path) as archive:
            if "xl/styles.xml" not in archive.namelist():
                continue
            stylesheet = ET.fromstring(archive.read("xl/styles.xml"))
            styles = stylesheet.find(ns + "cellXfs")
            count = len(Stylesheet.from_tree(stylesheet).cell_styles)
            if styles is not None and any(child.tag.endswith("}AlternateContent") for child in styles):
                alternate_styles.append(item["document_id"])
            maximum = max((int(cell.attrib.get("s", "0"))
                           for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
                           for cell in ET.fromstring(archive.read(name)).iter(ns + "c")), default=0)
            if maximum >= count:
                style_failures.append(item["document_id"])
    result["reader_style_table_incompatible_documents"] = style_failures
    result["alternate_content_style_documents"] = alternate_styles
    if failures or lint["status"] != "PASS":
        result["status"] = "FAIL"
    if args.output:
        atomic_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
