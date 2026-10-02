from __future__ import annotations

from pathlib import Path
from collections import Counter

from config.settings import Settings
from .io import atomic_json
from .validation import read_json
from .web_bridge import WebDataBridge, tree_digest
from .menu_lint import scan_public_menus, require_clean_public_menus
from parsers.excel.menu_artifacts import CATEGORIES


def capture_baseline(settings: Settings | None = None) -> dict:
    bridge = WebDataBridge(settings)
    pointer, run, report = bridge.active_run()
    path = bridge.settings.production_root / "reports/menu_quality_before.json"
    if path.exists():
        existing = read_json(path)
        if existing["dataset_version"] == pointer["dataset_version"]:
            if tree_digest(run) != existing["immutable_run_sha256"]:
                raise ValueError("old immutable run differs from saved baseline")
            # Re-scan the same unchanged source when the deterministic rules
            # are refined; preserve the original identity/hash, never its data.
            existing["scan"] = scan_public_menus(run / "web_data")
            atomic_json(path, existing)
            return existing
        raise ValueError("baseline already exists for another dataset; refusing to overwrite")
    result = {"dataset_version": pointer["dataset_version"], "run_path": pointer["run_path"],
              "immutable_run_sha256": tree_digest(run), "documents": report["documents"],
              "meal_slots": report["records"]["production_ready"],
              "scan": scan_public_menus(run / "web_data")}
    atomic_json(path, result)
    return result


def compare_quality(settings: Settings | None = None) -> dict:
    bridge = WebDataBridge(settings)
    pointer, run, report = bridge.active_run()
    baseline = read_json(bridge.settings.production_root / "reports/menu_quality_before.json")
    old_run = bridge.settings.production_root / baseline["run_path"]
    old_report = read_json(old_run / "reports/excel_production_report.json")
    unchanged = tree_digest(old_run) == baseline["immutable_run_sha256"]
    if not unchanged:
        raise ValueError("old immutable run changed")
    regressions = {}
    actions = Counter()
    for route in ("ready", "review", "failed"):
        for path in (run / route).glob("*.json"):
            value = read_json(path)
            for artifact in value.get("menu_artifacts", []):
                actions[(artifact["classification"], artifact["action"])] += 1
    for document_id in ("65664-66430", "65691-66457", "65649-66413", "72303-74034"):
        path = next((run / route / f"{document_id}.json" for route in ("ready", "review", "failed")
                     if (run / route / f"{document_id}.json").exists()), None)
        if path is None:
            raise ValueError(f"missing regression document {document_id}")
        value = read_json(path)
        regressions[document_id] = {"route": value["production_status"], "status": value["status"],
                                    **{key: value.get(key) for key in
                                       ("menu_quality_valid", "resolved_formula_cells", "unresolved_formula_values",
                                        "artifact_counts", "excluded_artifacts", "coverage")}}
    result = {"old_dataset": baseline["dataset_version"], "new_dataset": pointer["dataset_version"],
              "old_immutable_run_unchanged": unchanged,
              "source_corpus_unchanged": old_report["run_metadata"]["source_corpus_version"] == report["run_metadata"]["source_corpus_version"],
              "before": {"documents": baseline["documents"], "meal_slots": baseline["meal_slots"],
                         "scan": {k: v for k, v in baseline["scan"].items() if k != "occurrences"}},
              "after": {"documents": report["documents"], "meal_slots": report["records"]["production_ready"],
                        "month_files": report["web_data"]["institution_month_files"], "menu_quality": report["menu_quality"],
                        "artifact_actions": {category: {
                            "excluded_from_menu": actions[(category, "excluded_from_menu")],
                            "quarantined": actions[(category, "quarantined")]} for category in CATEGORIES},
                        "public_lint": require_clean_public_menus(run / "web_data")},
              "regressions": regressions}
    atomic_json(bridge.settings.production_root / "reports/menu_quality_comparison.json", result)
    return result
