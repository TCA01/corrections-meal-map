from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from config.settings import Settings
from .io import atomic_json
from .validation import read_json, validate_dataset
from .web_contract import CONTRACT_VERSION, SCHEMA_VERSION, validate_web_bundle
from .menu_lint import require_clean_public_menus


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def promote_directory(staged: Path, destination: Path, validator, *, backup_root: Path | None = None) -> Path | None:
    """Whole-directory rename with retained backup and rollback, never per-file merge.

    Portable filesystems cannot atomically replace a non-empty directory in one
    operation. Two renames have a brief missing-path interval; exceptions roll
    back. A journal permits recovery after a process crash during the interval.
    """
    if staged.parent != destination.parent or destination.is_symlink():
        raise ValueError("staging must share destination parent; destination must not be a symlink")
    validator(staged)
    journal = destination.parent / f".{destination.name}.swap.json"
    if journal.exists():
        raise ValueError("unfinished directory swap; recover it before promotion")
    backup_root = backup_root or destination.parent
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / f".{destination.name}.previous-{uuid.uuid4().hex}"
    atomic_json(journal, {"destination": destination.name, "staged": staged.name, "backup": backup.name,
                          "backup_root": str(backup_root.resolve())})
    moved_old = False
    moved_new = False
    try:
        if destination.exists():
            os.replace(destination, backup)
            moved_old = True
        os.replace(staged, destination)
        moved_new = True
        validator(destination)
    except BaseException:
        if moved_old:
            if destination.exists():
                rejected = backup_root / f".{destination.name}.rejected-{uuid.uuid4().hex}"
                os.replace(destination, rejected)
            os.replace(backup, destination)
        elif moved_new:
            os.replace(destination, staged)
        journal.unlink(missing_ok=True)
        raise
    journal.unlink(missing_ok=True)
    return backup if moved_old else None


def recover_directory_swap(destination: Path, *, backup_root: Path | None = None) -> None:
    journal = destination.parent / f".{destination.name}.swap.json"
    if not journal.exists():
        return
    value = read_json(journal)
    if value.get("destination") != destination.name:
        raise ValueError("directory swap journal identity mismatch")
    for field in ("staged", "backup"):
        if Path(value[field]).name != value[field] or not value[field].startswith(f".{destination.name}."):
            raise ValueError("unsafe directory swap journal")
    backup_root = backup_root or destination.parent
    if value.get("backup_root") != str(backup_root.resolve()):
        raise ValueError("directory swap backup root mismatch")
    backup = backup_root / value["backup"]
    # Prefer restoring the known previous tree after any interrupted swap.
    if backup.exists():
        if destination.exists():
            os.replace(destination, backup_root / f".{destination.name}.recovered-{uuid.uuid4().hex}")
        os.replace(backup, destination)
    journal.unlink()


class WebDataBridge:
    def __init__(self, settings: Settings | None = None, *, expected_master_count: int = 55) -> None:
        self.settings = settings or Settings()
        self.expected_master_count = expected_master_count

    @property
    def deploy_path(self) -> Path:
        return self.settings.production_root / "deploy/web_data"

    def active_run(self) -> tuple[dict[str, Any], Path, dict[str, Any]]:
        pointer = read_json(self.settings.production_root / "current.json")
        run = (self.settings.production_root / pointer["run_path"]).resolve()
        if not run.is_relative_to((self.settings.production_root / "runs").resolve()):
            raise ValueError("active run is outside production/runs")
        report = read_json(run / "reports/excel_production_report.json")
        if report["run_metadata"]["dataset_version"] != pointer["dataset_version"]:
            raise ValueError("active pointer/report version mismatch")
        return pointer, run, report

    def _public_master(self) -> list[dict[str, Any]]:
        return [{
            "institution_id": i["institution_id"], "name": i["canonical_name"], "short_name": i.get("short_name"),
            "type": i["institution_type"], "address": i["address"], "postal_code": i.get("postal_code"),
            "phone": i.get("phone"), "latitude": i.get("latitude"), "longitude": i.get("longitude"),
            "source_url": i["source_url"], "active": i["active"],
        } for i in read_json(self.settings.institutions_path)]

    def validate(self, path: Path) -> dict[str, Any]:
        pointer, run, report = self.active_run()
        result = validate_web_bundle(path, expected_version=pointer["dataset_version"],
                                     expected_master_count=self.expected_master_count, report=report)
        result["menu_lint"] = require_clean_public_menus(path)
        if read_json(path / "institutions.json") != self._public_master():
            raise ValueError("export differs from official institution master")
        if tree_digest(path / "menus") != tree_digest(run / "web_data/menus"):
            raise ValueError("menus differ from immutable READY source")
        if read_json(self.settings.production_root / "current.json") != pointer:
            raise ValueError("active dataset changed during validation")
        return result

    def build(self) -> dict[str, Any]:
        pointer, run, report = self.active_run()
        before = tree_digest(run)
        master = read_json(self.settings.institutions_path)
        validate_dataset(run, report, {i["institution_id"] for i in master})
        destination = self.deploy_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        recover_directory_swap(destination)
        staged = Path(tempfile.mkdtemp(prefix=".web_data.staging-", dir=destination.parent))
        shutil.copytree(run / "web_data/menus", staged / "menus")
        public_master = self._public_master()
        source_manifest = read_json(run / "web_data/manifest.json")
        metadata = report["run_metadata"]
        manifest = {
            "schema_version": SCHEMA_VERSION, "web_contract_version": CONTRACT_VERSION,
            "dataset_version": pointer["dataset_version"], "generated_at": metadata["generated_at"],
            "institutions": [{"institution_id": row["institution_id"], "available_years": row["available_years"]}
                             for row in source_manifest["institutions"]],
            "stats": {
                "total_institutions": len(public_master), "collected_institutions": report["institution_coverage"]["production_ready"],
                "structured_documents": report["documents"]["ready"], "total_meal_records": report["records"]["production_ready"],
                "institution_month_files": report["web_data"]["institution_month_files"],
                "last_updated": metadata["generated_at"], "data_scope": "excel_ready_only",
            },
        }
        atomic_json(staged / "institutions.json", public_master)
        atomic_json(staged / "manifest.json", manifest)
        validator = self.validate
        if read_json(self.settings.production_root / "current.json") != pointer or tree_digest(run) != before:
            raise ValueError("active run changed while building bridge")
        backup = promote_directory(staged, destination, validator)
        evidence = {**validator(destination), "immutable_run_unchanged": tree_digest(run) == before,
                    "run_sha256_before": before, "run_sha256_after": tree_digest(run),
                    "previous_bundle": str(backup) if backup else None}
        atomic_json(self.settings.production_root / "reports/web_bridge_build.json", evidence)
        return evidence

    def sync(self) -> dict[str, Any]:
        pointer, _, report = self.active_run()
        source = self.deploy_path
        validator = self.validate
        validator(source)
        destination = self.settings.project_root / "web/public/web_data"
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Backups (especially W1 mocks) must never be served from web/public.
        backup_root = self.settings.project_root / "web/tests/fixtures/web_data/backups"
        recover_directory_swap(destination, backup_root=backup_root)
        if destination.exists() and read_json(destination / "manifest.json").get("is_mock_fixture") is True:
            fixture = self.settings.project_root / "web/tests/fixtures/web_data/w1"
            if fixture.exists():
                if tree_digest(fixture) != tree_digest(destination):
                    raise ValueError("existing W1 fixture differs; refusing to overwrite it")
            else:
                fixture.parent.mkdir(parents=True, exist_ok=True)
                fixture_stage = Path(tempfile.mkdtemp(prefix=".w1.staging-", dir=fixture.parent))
                shutil.copytree(destination, fixture_stage, dirs_exist_ok=True)
                if tree_digest(destination) != tree_digest(fixture_stage):
                    raise ValueError("mock fixture copy mismatch")
                os.replace(fixture_stage, fixture)
        staged = Path(tempfile.mkdtemp(prefix=".web_data.staging-", dir=destination.parent))
        source_digest = tree_digest(source)
        shutil.copytree(source, staged, dirs_exist_ok=True)
        if tree_digest(staged) != source_digest or tree_digest(source) != source_digest:
            raise ValueError("deploy/copy contents differ")
        if read_json(self.settings.production_root / "current.json") != pointer:
            raise ValueError("active dataset changed during sync")
        backup = promote_directory(staged, destination, validator, backup_root=backup_root)
        if tree_digest(destination) != source_digest:
            raise ValueError("synced bundle hash mismatch")
        evidence = {**validator(destination), "copied_tree_sha256": source_digest,
                    "previous_web_data": str(backup) if backup else None, "swap_policy": "staged_rename_with_rollback"}
        atomic_json(self.settings.production_root / "reports/web_bridge_sync.json", evidence)
        return evidence

    def build_fixtures(self) -> dict[str, Any]:
        source = self.deploy_path
        self.validate(source)
        candidates = []
        for path in sorted((source / "menus").rglob("*.json")):
            month = read_json(path)
            multi_types = {meal_type for meals in month["days"].values() for meal_type, slot in meals.items()
                           if len(slot["menu_items"]) > 1}
            candidates.append((len(multi_types), path, month))
        candidates.sort(key=lambda item: (-item[0], item[1].as_posix()))
        selected = []
        for candidate in candidates:
            if not selected or candidate[2]["institution_id"] != selected[0][2]["institution_id"]:
                selected.append(candidate)
            if len(selected) == 2:
                break
        if len(selected) < 2:
            selected = candidates[:2]
        if len(selected) < 2 or any(score != 3 for score, _, _ in selected):
            raise ValueError("need two real months with multi-item breakfast/lunch/dinner")
        destination = self.settings.project_root / "web/tests/fixtures/web_contract/web_data"
        destination.parent.mkdir(parents=True, exist_ok=True)
        recover_directory_swap(destination)
        staged = Path(tempfile.mkdtemp(prefix=".web_data.staging-", dir=destination.parent))
        index: dict[str, dict[str, list[int]]] = {}
        documents = set()
        meal_count = 0
        for _, path, month in selected:
            target = staged / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            index.setdefault(month["institution_id"], {}).setdefault(str(month["year"]), []).append(month["month"])
            documents.update(s["document_id"] for s in month["sources"])
            meal_count += sum(len(meals) for meals in month["days"].values())
        shutil.copyfile(source / "institutions.json", staged / "institutions.json")
        manifest = read_json(source / "manifest.json")
        manifest["institutions"] = [{"institution_id": i, "available_years": {year: sorted(months) for year, months in years.items()}}
                                    for i, years in sorted(index.items())]
        manifest["stats"].update(collected_institutions=len(index), structured_documents=len(documents),
                                 total_meal_records=meal_count, institution_month_files=2)
        atomic_json(staged / "manifest.json", manifest)
        validator = lambda path: validate_web_bundle(path, expected_master_count=self.expected_master_count,
                                                    expected_version=manifest["dataset_version"])
        promote_directory(staged, destination, validator)
        evidence = {**validator(destination), "fixture_policy": "real_ready_excerpt_not_deployable",
                    "multi_item_meal_types": ["breakfast", "lunch", "dinner"]}
        atomic_json(destination.parent / "fixture_info.json", evidence)
        return evidence
