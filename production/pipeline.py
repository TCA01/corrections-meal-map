from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import Settings
from institutions.master import InstitutionMaster
from parsers.excel import ExcelMealParser

from .gate import production_route
from .io import atomic_json, atomic_jsonl, read_jsonl, verified_file
from .validation import KNOWN_LAYOUTS, validate_dataset, validate_public_source, validate_record
from .menu_lint import require_clean_public_menus
from parsers.excel.menu_artifacts import CATEGORIES


PARSER_VERSION = "3B.2"
SCHEMA_VERSION = "1.0"
PRODUCTION_POLICY_VERSION = "3B.2"


def detect_conflicts(documents: list[dict[str, Any]]) -> tuple[set[str], list[dict[str, Any]], int]:
    slots: dict[tuple[str, str, str], list[tuple[str, tuple[str, ...]]]] = defaultdict(list)
    for document in documents:
        document_id = str(document["document_id"])
        for record in document["result"].get("records", []):
            key = (str(record.get("institution_id")), str(record.get("meal_date")), str(record.get("meal_type")))
            content = tuple(str(item.get("name", "")).strip() for item in record.get("menu_items", []))
            slots[key].append((document_id, content))
    affected: set[str] = set()
    conflicts = []
    duplicate_count = 0
    for key, candidates in slots.items():
        variants: dict[tuple[str, ...], set[str]] = defaultdict(set)
        for document_id, content in candidates:
            variants[content].add(document_id)
        duplicate_count += max(0, len(candidates) - len(variants))
        if len(variants) <= 1:
            continue
        ids = sorted({document_id for document_id, _ in candidates})
        affected.update(ids)
        conflicts.append({
            "code": "DATA_CONFLICT", "institution_id": key[0], "meal_date": key[1],
            "meal_type": key[2], "document_ids": ids,
            "variants": [{"menu_items": list(content), "document_ids": sorted(doc_ids)}
                         for content, doc_ids in sorted(variants.items())],
        })
    return affected, conflicts, duplicate_count


class ProductionExcelPipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.parser = ExcelMealParser(self.settings.project_root)

    def run(self, *, resume: bool = True, limit: int | None = None,
            from_checkpoint: int | None = None, new_run: bool = False) -> dict[str, Any]:
        manifest = read_jsonl(self.settings.production_manifest_path)
        if not manifest or any(i.get("download_status") in {None, "pending", "discovered"} for i in manifest):
            raise ValueError("download manifest is empty or incomplete; finish download before production parsing")
        checkpoint = self._checkpoint() if resume and not new_run else {}
        input_version = self._input_version(manifest)
        if checkpoint and checkpoint.get("input_version") != input_version:
            raise ValueError("parse inputs changed since checkpoint; use --new-run")
        if checkpoint.get("completed"):
            return json.loads((self.settings.production_root / "runs" / checkpoint["run_id"] /
                               "reports/excel_production_report.json").read_text(encoding="utf-8"))
        run_id = str(checkpoint.get("run_id") or self._run_id(manifest))
        final = self.settings.production_root / "runs" / run_id
        if final.exists():
            # Recover a crash between immutable directory promotion and pointer publication.
            report = json.loads((final / "reports/excel_production_report.json").read_text(encoding="utf-8"))
            self._validate_staging(final, report)
            self._publish_pointer(final, run_id)
            report["atomic_publication"] = "PASS"
            atomic_json(final / "reports/excel_production_report.json", report)
            self._save_checkpoint(run_id, len(manifest), len(manifest), input_version, completed=True)
            atomic_json(self.settings.production_root / "reports/excel_production_report.json", report)
            return report
        staging = self.settings.production_root / ".staging" / run_id
        results_root = staging / "parsed"
        results_root.mkdir(parents=True, exist_ok=True)
        start = int(from_checkpoint if from_checkpoint is not None else checkpoint.get("next_index", 0))
        start = max(0, min(start, len(manifest)))
        stop = len(manifest) if limit is None else min(len(manifest), start + max(limit, 0))
        for item in manifest[:start]:
            if item.get("download_status") != "failed" and not (results_root / f"{item['document_id']}.json").is_file():
                raise ValueError("parse checkpoint refers to missing staging result; use --new-run")
        self._save_checkpoint(run_id, start, len(manifest), input_version)
        for index in range(start, stop):
            item = manifest[index]
            if item.get("download_status") in {"downloaded", "reused", "deduplicated"} and item.get("local_path"):
                try:
                    if not verified_file(self.settings.project_root, item):
                        result = self.parser._failed(item, "RAW_INTEGRITY_FAILED", "raw SHA-256/size/path verification failed")
                    else:
                        result = self.parser.parse_sample(item)
                except Exception as error:  # isolate each document
                    result = self.parser._failed(item, "PARSER_EXCEPTION", f"{type(error).__name__}: {error}")
                atomic_json(results_root / f"{item['document_id']}.json", result)
                item["parser_status"] = "parsed" if result.get("status") != "FAIL" else "failed"
            else:
                item["parser_status"] = "not_parsed"
            atomic_jsonl(self.settings.production_manifest_path, manifest)
            self._save_checkpoint(run_id, index + 1, len(manifest), input_version)
            if (index + 1) % 50 == 0:
                print(f"Parsed {index + 1}/{len(manifest)}", flush=True)
        if stop < len(manifest):
            return {"run_id": run_id, "completed": False, "next_index": stop, "target": len(manifest)}
        report = self._finalize(run_id, staging, manifest)
        self._save_checkpoint(run_id, len(manifest), len(manifest), input_version, completed=True)
        return report

    def _finalize(self, run_id: str, staging: Path, manifest: list[dict[str, Any]]) -> dict[str, Any]:
        parsed = []
        master = InstitutionMaster.load(self.settings.institutions_path)
        canonical_ids = {institution.institution_id for institution in master.institutions}
        for item in manifest:
            path = staging / "parsed" / f"{item['document_id']}.json"
            if path.exists():
                result = json.loads(path.read_text(encoding="utf-8"))
            else:
                if item.get("download_status") != "failed":
                    raise ValueError(f"missing parsed result for downloaded document {item['document_id']}")
                result = self.parser._failed(item, "DOWNLOAD_FAILED", item.get("error") or "file unavailable")
            institution_id = item.get("institution_id")
            route = production_route(result, institution_id=institution_id if institution_id in canonical_ids else None)
            if institution_id not in canonical_ids:
                result.setdefault("document_issues", []).append({
                    "code": "UNRESOLVED_INSTITUTION", "severity": "warning",
                    "message": "institution not present in canonical master; no inferred mapping",
                })
            unknown_layouts = {p.get("detected_layout_family") for p in result.get("layout_profiles", [])} - KNOWN_LAYOUTS
            if unknown_layouts:
                result.setdefault("document_issues", []).append({
                    "code": "NEW_LAYOUT_CANDIDATE", "severity": "warning",
                    "message": f"unrecognized layout families: {sorted(str(x) for x in unknown_layouts)}",
                })
                if route == "ready":
                    route = "review"
            if route == "ready":
                try:
                    validate_public_source(self._public_source(item))
                    if not result.get("records"):
                        raise ValueError("ready document has no records")
                    for record in result["records"]:
                        validate_record(record, institution_id=institution_id)
                except (ValueError, KeyError, TypeError, AttributeError) as error:
                    route = "review"
                    result.setdefault("document_issues", []).append({
                        "code": "PRODUCTION_SCHEMA_INVALID", "severity": "warning", "message": str(error),
                    })
            parsed.append({"document_id": item["document_id"], "manifest": item, "result": result, "route": route})

        initially_ready = [item for item in parsed if item["route"] == "ready"]
        affected, conflicts, duplicate_count = detect_conflicts(initially_ready)
        for item in parsed:
            if item["document_id"] in affected:
                item["route"] = "review"
                item["result"].setdefault("document_issues", []).append({
                    "code": "DATA_CONFLICT", "severity": "warning",
                    "message": "conflicting production-eligible source for an institution/date/meal slot",
                })
            item["manifest"]["production_status"] = item["route"]

        self._write_routes(staging, parsed)
        web_stats = self._write_web_data(staging / "web_data", parsed, run_id)
        report = self._report(run_id, manifest, parsed, conflicts, duplicate_count, web_stats)
        atomic_json(staging / "reports" / "excel_production_report.json", report)
        atomic_json(staging / "metadata.json", report["run_metadata"])
        atomic_jsonl(staging / "excel_manifest.jsonl", manifest)
        atomic_jsonl(self.settings.production_manifest_path, manifest)
        self._validate_staging(staging, report)
        # Persist the result of the checks actually performed, before publication.
        report["schema_validation"] = self._validation_result
        atomic_json(staging / "reports/excel_production_report.json", report)
        if report["records"]["production_ready"] == 0 and (self.settings.production_root / "current.json").exists():
            raise ValueError("refusing to replace an existing publication with an empty ready dataset")
        final = self.settings.production_root / "runs" / run_id
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            raise FileExistsError(f"run already exists: {final}")
        os.replace(staging, final)
        self._publish_pointer(final, run_id)
        report["atomic_publication"] = "PASS"
        atomic_json(final / "reports/excel_production_report.json", report)
        reports = self.settings.production_root / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        atomic_json(reports / "excel_production_report.json", report)
        return report

    def _write_routes(self, staging: Path, parsed: list[dict[str, Any]]) -> None:
        for item in parsed:
            result = deepcopy(item["result"])
            result["document_id"] = item["document_id"]
            result["production_status"] = item["route"]
            result["parser_gate_eligible"] = result.get("production_eligible")
            result["production_eligible"] = item["route"] == "ready"
            result["source_metadata"] = self._public_source(item["manifest"])
            for other_route in {"ready", "review", "failed"} - {item["route"]}:
                (staging / other_route / f"{item['document_id']}.json").unlink(missing_ok=True)
            atomic_json(staging / item["route"] / f"{item['document_id']}.json", result)

    def _write_web_data(self, root: Path, parsed: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
        ready = [item for item in parsed if item["route"] == "ready"]
        master = InstitutionMaster.load(self.settings.institutions_path)
        institutions_by_id = {item.institution_id: item for item in master.institutions}
        monthly: dict[tuple[str, int, int], dict[str, Any]] = {}
        seen_slots: set[tuple[str, str, str, tuple[str, ...]]] = set()
        for document in sorted(ready, key=lambda item: item["document_id"]):
            source = self._public_source(document["manifest"])
            for record in document["result"].get("records", []):
                date = str(record["meal_date"])
                year, month = int(date[:4]), int(date[5:7])
                key = (str(record["institution_id"]), year, month)
                bucket = monthly.setdefault(key, {
                    "schema_version": SCHEMA_VERSION, "institution_id": key[0],
                    "year": year, "month": month, "days": {}, "sources": {},
                })
                names = tuple(str(menu["name"]) for menu in record.get("menu_items", []))
                slot = (key[0], date, str(record["meal_type"]), names)
                bucket["sources"][document["document_id"]] = source
                if slot in seen_slots:
                    meal = bucket["days"][date][record["meal_type"]]
                    if document["document_id"] not in meal["source_document_ids"]:
                        meal["source_document_ids"].append(document["document_id"])
                    continue
                seen_slots.add(slot)
                bucket["days"].setdefault(date, {})[record["meal_type"]] = {
                    "menu_items": list(record.get("menu_items", [])),
                    "source_document_id": document["document_id"],
                    "source_document_ids": [document["document_id"]],
                    "source": source,
                }
        index: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
        for (institution_id, year, month), value in monthly.items():
            value["sources"] = list(value["sources"].values())
            atomic_json(root / "menus" / institution_id / str(year) / f"{month:02d}.json", value)
            index[institution_id][str(year)].add(month)
        institution_rows = []
        for institution_id in sorted(index):
            institution = institutions_by_id.get(institution_id)
            institution_rows.append({
                "institution_id": institution_id,
                "name": institution.canonical_name if institution else institution_id,
                "available_years": {year: sorted(months) for year, months in sorted(index[institution_id].items())},
            })
        atomic_json(root / "institutions.json", institution_rows)
        atomic_json(root / "manifest.json", {
            "schema_version": SCHEMA_VERSION, "dataset_version": run_id,
            "generated_at": self._now(), "institutions": institution_rows,
        })
        return {"institution_month_files": len(monthly), "institutions": len(institution_rows),
                "unique_records": len(seen_slots)}

    def _report(self, run_id: str, manifest: list[dict[str, Any]], parsed: list[dict[str, Any]],
                conflicts: list[dict[str, Any]], duplicate_count: int,
                web_stats: dict[str, Any]) -> dict[str, Any]:
        routes = Counter(item["route"] for item in parsed)
        download = Counter(item.get("download_status") for item in manifest)
        all_records = [record for item in parsed for record in item["result"].get("records", [])]
        ready_records = [record for item in parsed if item["route"] == "ready"
                         for record in item["result"].get("records", [])]
        record_states = Counter(record.get("validation_status") for record in all_records)
        formats = {}
        for extension in ("xlsx", "xls"):
            subset = [item for item in parsed if item["manifest"].get("extension") == extension]
            formats[extension] = {route: sum(item["route"] == route for item in subset)
                                  for route in ("ready", "review", "failed")}
        actual_formats = {extension: {route: sum(item["result"].get("detected_format") == extension
                                                and item["route"] == route for item in parsed)
                                     for route in ("ready", "review", "failed")}
                          for extension in ("xlsx", "xls", None)}
        family_docs: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in parsed:
            families = {p.get("detected_layout_family", "unknown") for p in item["result"].get("layout_profiles", [])}
            if not families:
                families = {"undetected"}
            for family in families:
                family_docs[str(family)].append(item)
        layouts = {family: {"documents": len(items), **dict(Counter(i["route"] for i in items))}
                   for family, items in sorted(family_docs.items())}
        issues = Counter(
            issue.get("code") for item in parsed for issue in item["result"].get("document_issues", [])
        )
        failures = Counter(
            failure.get("code") for item in parsed for failure in item["result"].get("failures", [])
        )
        new_layouts = [{"document_id": item["document_id"], "filename": item["manifest"].get("filename"),
                       "issues": item["result"].get("failures", []) + item["result"].get("document_issues", []),
                       "layout_profiles": item["result"].get("layout_profiles", [])}
                       for item in parsed if any(f.get("code") == "UNSUPPORTED_LAYOUT"
                                                for f in item["result"].get("failures", []))
                       or any(i.get("code") == "NEW_LAYOUT_CANDIDATE" for i in item["result"].get("document_issues", []))]
        ready_institutions = {r.get("institution_id") for r in ready_records if r.get("institution_id")}
        source_institutions = {i.get("institution_id") for i in manifest if i.get("institution_id")}
        dates = sorted({str(r["meal_date"]) for r in ready_records})
        pairs = {(r.get("institution_id"), r.get("meal_date")) for r in ready_records}
        source_version = hashlib.sha256("\n".join(
            f"{i['document_id']}:{i.get('sha256') or ''}" for i in manifest
        ).encode()).hexdigest()
        return {
            "run_metadata": {
                "dataset_version": run_id, "generated_at": self._now(),
                "source_corpus_version": source_version, "parser_version": PARSER_VERSION,
                "production_policy_version": PRODUCTION_POLICY_VERSION,
                "schema_version": SCHEMA_VERSION, "documents_total": len(manifest),
                "ready": routes["ready"], "review": routes["review"], "failed": routes["failed"],
                "meal_records": web_stats["unique_records"],
            },
            "documents": {
                "target": len(manifest), "downloaded": download["downloaded"],
                "reused": download["reused"], "deduplicated": download["deduplicated"],
                "download_failed": download["failed"],
                "parsed": sum(i["manifest"].get("parser_status") in {"parsed", "failed"} for i in parsed),
                "ready": routes["ready"], "review": routes["review"], "failed": routes["failed"],
            },
            "records": {"generated": len(all_records), "production_ready": web_stats["unique_records"],
                        "ready_source_records": len(ready_records),
                        "warning": record_states["warning"], "invalid": record_states["invalid"]},
            "formats": formats, "actual_formats": actual_formats, "layout_families": layouts,
            "parser_results": dict(Counter(i["result"].get("status") for i in parsed)),
            "format_extension_mismatches": sum(bool(i["result"].get("format_extension_mismatch")) for i in parsed),
            "validation_issues": dict(issues), "failure_codes": dict(failures),
            "new_layout_candidates": new_layouts,
            "institution_coverage": {"excel_source": len(source_institutions), "production_ready": len(ready_institutions)},
            "date_coverage": {"earliest": dates[0] if dates else None, "latest": dates[-1] if dates else None,
                              "unique_institution_date_pairs": len(pairs)},
            "conflicts": conflicts,
            "conflicting_documents": len({doc_id for c in conflicts for doc_id in c["document_ids"]}),
            "identical_content_duplicates": len(ready_records) - web_stats["unique_records"],
            "identical_content_duplicates_initial_candidates": duplicate_count,
            "unresolved_institution": sum(not i.get("institution_id") for i in manifest),
            "download_failures": [i["document_id"] for i in manifest if i.get("download_status") == "failed"],
            "download_failure_details": [{"document_id": i["document_id"], "download_url": i.get("download_url"),
                                           "error": i.get("error")} for i in manifest if i.get("download_status") == "failed"],
            "web_data": web_stats, "atomic_publication": "PENDING",
            "menu_quality": {
                **{key: sum(int(i["result"].get(key, 0)) for i in parsed) for key in
                   ("resolved_formula_cells", "unresolved_formula_values", "excel_error_menu_items",
                    "unresolved_non_menu_artifacts", "excluded_artifacts", "unresolved_slots")},
                "artifact_counts": {category: sum(i["result"].get("artifact_counts", {}).get(category, 0)
                                                   for i in parsed) for category in CATEGORIES},
                "artifact_occurrence_unit": "extracted_meal_item (weekly source may repeat across dates)",
                "formula_count_unit": "unique consumed sheet/cell per document",
                "documents_quality_valid": sum(i["result"].get("menu_quality_valid") is True for i in parsed),
            },
        }

    @staticmethod
    def _public_source(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "document_id": item.get("document_id") or f"{item.get('post_id')}-{item.get('attachment_id')}",
            "post_id": item.get("post_id"), "attachment_id": item.get("attachment_id"),
            "post_url": item.get("post_url"), "download_url": item.get("download_url"),
            "original_filename": item.get("filename"), "published_date": item.get("published_date"),
        }

    def _validate_staging(self, staging: Path, report: dict[str, Any]) -> None:
        master = InstitutionMaster.load(self.settings.institutions_path)
        self._validation_result = validate_dataset(staging, report, {i.institution_id for i in master.institutions})
        self._validation_result["menu_lint"] = require_clean_public_menus(staging / "web_data")

    def _publish_pointer(self, final: Path, run_id: str) -> None:
        atomic_json(self.settings.production_root / "current.json", {
            "dataset_version": run_id, "run_path": final.relative_to(self.settings.production_root).as_posix(),
            "published_at": self._now(),
        })

    def _save_checkpoint(self, run_id: str, next_index: int, target: int, input_version: str,
                         *, completed: bool = False) -> None:
        atomic_json(self.settings.production_parse_checkpoint_path, {
            "run_id": run_id, "input_version": input_version, "next_index": next_index, "target": target,
            "completed": completed, "published": completed, "updated_at": self._now(),
        })

    def _input_version(self, manifest: list[dict[str, Any]]) -> str:
        fields = ("document_id", "sha256", "local_path", "file_size", "institution_id", "filename", "extension",
                  "meal_year", "meal_month", "published_date", "post_url", "download_url", "metadata_year_inferred",
                  "period_metadata", "document_role")
        data = [{k: item.get(k) for k in fields} for item in manifest]
        master_sha = hashlib.sha256(self.settings.institutions_path.read_bytes()).hexdigest()
        core_root = Path(__file__).resolve().parents[1] / "parsers/excel"
        core_sha = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(core_root.glob("*.py")))).hexdigest()
        return hashlib.sha256(json.dumps([PARSER_VERSION, PRODUCTION_POLICY_VERSION, data, master_sha, core_sha], sort_keys=True).encode()).hexdigest()

    def _checkpoint(self) -> dict[str, Any]:
        path = self.settings.production_parse_checkpoint_path
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    @staticmethod
    def _run_id(manifest: list[dict[str, Any]]) -> str:
        digest = hashlib.sha256("\n".join(str(i.get("sha256") or i["document_id"]) for i in manifest).encode()).hexdigest()[:10]
        return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z") + "-" + digest

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat()
