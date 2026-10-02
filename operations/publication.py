from __future__ import annotations

import os
import shutil
from collections import defaultdict
from copy import deepcopy

from production.io import atomic_json, atomic_jsonl, read_jsonl
from production.pipeline import ProductionExcelPipeline, detect_conflicts
from production.web_bridge import WebDataBridge, promote_directory, recover_directory_swap
from production.web_contract import validate_web_bundle, CONTRACT_VERSION
from production.menu_lint import require_clean_public_menus
from .state import load, now


def read_documents(run):
    return [{"document_id": item["document_id"], "manifest": item, "route": item["production_status"],
             "result": load(run / item["production_status"] / f"{item['document_id']}.json")}
            for item in read_jsonl(run / "excel_manifest.jsonl")]


def merge_ready(base, incoming):
    """Reject new conflicts, never demote the base. Recheck after restoring rejected replacements."""
    accepted = {doc["document_id"]: doc for doc in incoming}
    rejected = []
    while accepted:
        merged = {doc["document_id"]: doc for doc in base}
        merged.update(accepted)
        affected, _, _ = detect_conflicts([doc for doc in merged.values() if doc["route"] == "ready"])
        bad = affected & accepted.keys()
        if not bad:
            break
        rejected.extend(accepted.pop(key) for key in sorted(bad))
    merged = {doc["document_id"]: doc for doc in base}
    merged.update(accepted)
    return list(merged.values()), list(accepted.values()), rejected


def month_keys(documents):
    return {(r["institution_id"], int(r["meal_date"][:4]), int(r["meal_date"][5:7]))
            for doc in documents if doc["route"] == "ready" for r in doc["result"].get("records", [])}


class IncrementalPublisher:
    def __init__(self, settings, ops_root, master_count):
        self.settings = settings
        self.ops_root = ops_root
        self.pipeline = ProductionExcelPipeline(settings)
        self.bridge = WebDataBridge(settings, expected_master_count=master_count)
        self.master_count = master_count

    def recover(self):
        journal = self.ops_root / "publication_transaction.json"
        value = load(journal)
        if value:
            root = (self.ops_root / value["backup"]).resolve()
            if not root.is_relative_to((self.ops_root / "runs").resolve()):
                raise ValueError("unsafe publication recovery path")
            atomic_json(self.settings.production_root / "current.json", value["pointer"])
            for name, destination, backup_root in self.destinations():
                recover_directory_swap(destination, backup_root=backup_root)
                if (root / name).exists():
                    self.restore(root / name, destination, backup_root)
                elif value.get("previously_absent", {}).get(name) and destination.exists():
                    root.mkdir(parents=True, exist_ok=True)
                    os.replace(destination, root / f"{name}-rejected-{os.urandom(8).hex()}")
            journal.unlink()

    def destinations(self):
        return [("deploy", self.bridge.deploy_path, self.bridge.deploy_path.parent),
                ("frontend", self.settings.project_root / "web/public/web_data",
                 self.settings.project_root / "web/tests/fixtures/web_data/backups")]

    def restore(self, source, destination, backup_root):
        stage = destination.parent / f".web_data.restore-{os.urandom(8).hex()}"
        shutil.copytree(source, stage)
        promote_directory(stage, destination, lambda p: validate_web_bundle(p, expected_master_count=self.master_count),
                          backup_root=backup_root)

    def export(self, stage, report):
        public = stage / "prepared_web_data"
        shutil.copytree(stage / "web_data/menus", public / "menus")
        master = self.bridge._public_master()
        source = load(stage / "web_data/manifest.json")
        metadata = report["run_metadata"]
        atomic_json(public / "institutions.json", master)
        atomic_json(public / "manifest.json", {
            "schema_version": "1.0", "web_contract_version": CONTRACT_VERSION,
            "dataset_version": metadata["dataset_version"], "generated_at": metadata["generated_at"],
            "institutions": [{"institution_id": row["institution_id"], "available_years": row["available_years"]}
                             for row in source["institutions"]],
            "stats": {"total_institutions": len(master),
                      "collected_institutions": report["institution_coverage"]["production_ready"],
                      "structured_documents": report["documents"]["ready"],
                      "total_meal_records": report["records"]["production_ready"],
                      "institution_month_files": report["web_data"]["institution_month_files"],
                      "last_updated": metadata["generated_at"], "data_scope": "excel_ready_only"}})
        validate_web_bundle(public, expected_version=metadata["dataset_version"],
                            expected_master_count=self.master_count, report=report)
        require_clean_public_menus(public)
        return public

    def prepare(self, base_run, base_docs, merged, accepted, run_id):
        stage = self.settings.production_root / ".staging" / run_id
        if stage.exists():
            raise FileExistsError("staging identity already exists")
        # Copy immutable routed JSON, not reparsing old raw files.
        shutil.copytree(base_run, stage, ignore=shutil.ignore_patterns("prepared_web_data", "incremental_months", "parsed"))
        self.pipeline._write_routes(stage, accepted)
        old = {d["document_id"]: d for d in base_docs}
        touched = month_keys(accepted + [old[d["document_id"]] for d in accepted if d["document_id"] in old])
        subset = deepcopy([d for d in merged if d["route"] == "ready"])
        for document in subset:
            document["result"]["records"] = [r for r in document["result"]["records"]
                if (r["institution_id"], int(r["meal_date"][:4]), int(r["meal_date"][5:7])) in touched]
        subset = [d for d in subset if d["result"]["records"]]
        projected = stage / "incremental_months"
        self.pipeline._write_web_data(projected, subset, run_id)
        for institution, year, month in touched:
            relative = f"menus/{institution}/{year}/{month:02d}.json"
            target = stage / "web_data" / relative
            source = projected / relative
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            elif target.exists():
                # Only a READY replacement may remove its own obsolete source month.
                target.unlink()
        index = defaultdict(lambda: defaultdict(set))
        records = 0
        for path in (stage / "web_data/menus").rglob("*.json"):
            month = load(path)
            index[month["institution_id"]][str(month["year"])].add(month["month"])
            records += sum(len(meals) for meals in month["days"].values())
        names = {i["institution_id"]: i["name"] for i in self.bridge._public_master()}
        rows = [{"institution_id": i, "name": names[i],
                 "available_years": {year: sorted(months) for year, months in sorted(years.items())}}
                for i, years in sorted(index.items())]
        atomic_json(stage / "web_data/institutions.json", rows)
        atomic_json(stage / "web_data/manifest.json", {"schema_version": "1.0", "dataset_version": run_id,
                                                    "generated_at": now(), "institutions": rows})
        manifest = [d["manifest"] for d in merged]
        for d in merged:
            d["manifest"]["production_status"] = d["route"]
        stats = {"institution_month_files": sum(len(months) for years in index.values() for months in years.values()),
                 "institutions": len(rows), "unique_records": records}
        report = self.pipeline._report(run_id, manifest, merged, [], 0, stats)
        report["atomic_publication"] = "PASS"
        report["incremental"] = {"base_version": load(base_run / "metadata.json")["dataset_version"],
                                 "touched_months": [list(k) for k in sorted(touched)]}
        atomic_jsonl(stage / "excel_manifest.jsonl", manifest)
        atomic_json(stage / "metadata.json", report["run_metadata"])
        atomic_json(stage / "reports/excel_production_report.json", report)
        self.pipeline._validate_staging(stage, report)
        public = self.export(stage, report)
        # Prove all unaffected public months are byte-identical.
        for path in (base_run / "web_data/menus").rglob("*.json"):
            month = load(path)
            key = (month["institution_id"], month["year"], month["month"])
            if key not in touched and path.read_bytes() != (stage / "web_data" / path.relative_to(base_run / "web_data")).read_bytes():
                raise ValueError("unaffected month changed")
        return stage, public, report, touched

    def publish(self, stage, public, report, run_id, run_root):
        pointer = load(self.settings.production_root / "current.json")
        if pointer != self.expected_pointer:
            raise ValueError("active production changed while preparing update")
        backup = run_root / "publication_backup"
        stages = []
        absent = {}
        for name, destination, backup_root in self.destinations():
            destination.parent.mkdir(parents=True, exist_ok=True)
            recover_directory_swap(destination, backup_root=backup_root)
            if destination.exists():
                shutil.copytree(destination, backup / name)
            else:
                absent[name] = True
            prepared = destination.parent / f".web_data.staging-{run_id}"
            shutil.copytree(public, prepared)
            validate_web_bundle(prepared, expected_version=run_id, expected_master_count=self.master_count, report=report)
            stages.append((prepared, destination, backup_root))
        journal = self.ops_root / "publication_transaction.json"
        if load(self.settings.production_root / "current.json") != pointer:
            raise ValueError("active production changed while staging web bundles")
        atomic_json(journal, {"pointer": pointer, "backup": backup.relative_to(self.ops_root).as_posix(),
                              "previously_absent": absent})
        final = self.settings.production_root / "runs" / run_id
        try:
            os.replace(stage, final)
            self.pipeline._publish_pointer(final, run_id)
            for prepared, destination, backup_root in stages:
                promote_directory(prepared, destination, self.bridge.validate, backup_root=backup_root)
            self.bridge.validate(self.bridge.deploy_path)
            self.bridge.validate(self.settings.project_root / "web/public/web_data")
            journal.unlink()
        except BaseException:
            self.recover()
            raise
        return report
