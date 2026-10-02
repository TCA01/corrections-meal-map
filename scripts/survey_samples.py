from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit.reporting import write_json
from audit.structure_survey import survey_file
from audit.template_families import build_template_families
from config.settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Survey structural complexity of locally downloaded samples")
    parser.add_argument(
        "--output",
        type=Path,
        default=Settings().historical_catalog_path.parent / "parser_structure_report.json",
    )
    parser.add_argument("--quiet", action="store_true", help="print counts instead of the full JSON report")
    parser.add_argument(
        "--template-output",
        type=Path,
        default=Settings().historical_catalog_path.parent / "template_families.json",
    )
    args = parser.parse_args()
    settings = Settings()
    samples = json.loads(settings.parser_samples_path.read_text(encoding="utf-8"))
    records = []
    seen: set[str] = set()
    for sample in samples:
        local_path = sample.get("local_path")
        if not local_path or str(local_path) in seen:
            continue
        path = settings.project_root / Path(*str(local_path).split("/"))
        if not path.is_file():
            records.append({
                "path": local_path,
                "filename": sample.get("filename"),
                "extension": sample.get("extension"),
                "survey_status": "failed",
                "reason": "downloaded sample file is missing",
                "post_id": sample.get("post_id"),
                "attachment_id": sample.get("attachment_id"),
                "institution_id": sample.get("institution_id"),
                "document_role": sample.get("document_role"),
            })
            continue
        seen.add(str(local_path))
        result = survey_file(path)
        result["path"] = local_path
        result.update({
            "post_id": sample.get("post_id"),
            "attachment_id": sample.get("attachment_id"),
            "institution_id": sample.get("institution_id"),
            "document_role": sample.get("document_role"),
        })
        records.append(result)
    report = {
        "surveyed_files": len(records),
        "successful_files": sum(1 for item in records if item.get("survey_status") == "ok"),
        "files": records,
    }
    write_json(args.output, report)
    write_json(args.template_output, build_template_families(records))
    if args.quiet:
        print(f"SURVEYED: {report['surveyed_files']}")
        print(f"SUCCESSFUL: {report['successful_files']}")
        print(f"FAILED: {report['surveyed_files'] - report['successful_files']}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["successful_files"] == report["surveyed_files"] and records else 1


if __name__ == "__main__":
    raise SystemExit(main())
