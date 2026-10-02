from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from config.settings import Settings
from production.io import atomic_json, atomic_jsonl
from production.validation import read_json
from production.web_bridge import WebDataBridge, promote_directory, recover_directory_swap, tree_digest
from production.web_contract import SOURCE_FIELDS, month_filename, validate_web_bundle


@pytest.fixture
def bridge(tmp_path: Path) -> WebDataBridge:
    cfg = replace(Settings(), project_root=tmp_path, production_root=tmp_path / "production",
                  institutions_path=tmp_path / "institutions.json")
    master = [{"institution_id": f"I{i}", "canonical_name": f"기관{i}", "short_name": None,
               "institution_type": "prison", "address": "공식 주소", "postal_code": None,
               "phone": None, "latitude": None, "longitude": None,
               "source_url": "https://example.test/official", "active": True} for i in range(55)]
    atomic_json(cfg.institutions_path, master)
    run = cfg.production_root / "runs/test-v1"
    source = {"document_id": "1-1", "post_id": "1", "attachment_id": "1",
              "post_url": "https://example.test/post/1", "download_url": "https://example.test/download/1",
              "original_filename": "meal.xlsx", "published_date": "2025-12-20"}
    records = []
    for month in (1, 2):
        day = f"2026-{month:02d}-01"
        meals = {}
        for meal_type in ("breakfast", "lunch", "dinner"):
            items = [{"name": "쌀밥", "raw_text": "쌀밥"}, {"name": "국", "raw_text": "국"}]
            meals[meal_type] = {"menu_items": items, "source_document_id": "1-1",
                                "source_document_ids": ["1-1"], "source": source}
            records.append({"institution_id": "I0", "meal_date": day, "meal_type": meal_type,
                            "menu_items": items, "schema_version": "1.0", "validation_status": "valid",
                            "parser": {"layout_family": "date_rows_meal_columns"},
                            "source": {"post_id": "1", "attachment_id": "1", "sheet": "Sheet1", "cells": ["B2"]}})
        atomic_json(run / f"web_data/menus/I0/2026/{month:02d}.json",
                    {"schema_version": "1.0", "institution_id": "I0", "year": 2026, "month": month,
                     "days": {day: meals}, "sources": [source]})
    availability = [{"institution_id": "I0", "name": "기관0", "available_years": {"2026": [1, 2]}}]
    atomic_json(run / "web_data/manifest.json", {"schema_version": "1.0", "dataset_version": "test-v1",
                                               "institutions": availability})
    atomic_json(run / "web_data/institutions.json", availability)
    atomic_json(run / "ready/1-1.json", {"document_id": "1-1", "production_status": "ready",
                                       "institution_id": "I0", "source_metadata": source, "records": records})
    atomic_jsonl(run / "excel_manifest.jsonl", [{"document_id": "1-1", "production_status": "ready"}])
    atomic_json(run / "reports/excel_production_report.json", {
        "run_metadata": {"dataset_version": "test-v1", "generated_at": "2026-10-01T17:00:00+09:00"},
        "documents": {"target": 1, "ready": 1, "review": 0, "failed": 0},
        "records": {"production_ready": 6}, "institution_coverage": {"production_ready": 1},
        "web_data": {"institution_month_files": 2}})
    atomic_json(cfg.production_root / "current.json", {"dataset_version": "test-v1", "run_path": "runs/test-v1"})
    return WebDataBridge(cfg)


def month_path(bridge: WebDataBridge) -> Path:
    return bridge.deploy_path / "menus/I0/2026/01.json"


def mutate(path: Path, change) -> None:
    value = read_json(path)
    change(value)
    atomic_json(path, value)


def test_full_55_master_export_with_null_coordinates(bridge):
    result = bridge.build()
    master = read_json(bridge.deploy_path / "institutions.json")
    assert len(master) == 55 and result["without_coordinates"] == 55
    assert all(i["latitude"] is None and i["longitude"] is None for i in master)
    assert all("name" in i and "type" in i and "canonical_name" not in i for i in master)


def test_availability_manifest_is_separate_from_master(bridge):
    bridge.build()
    assert read_json(bridge.deploy_path / "manifest.json")["institutions"] == [
        {"institution_id": "I0", "available_years": {"2026": [1, 2]}}]


def test_zero_padded_filename_contract(bridge):
    bridge.build()
    assert month_filename(7) == "07.json"
    month_path(bridge).rename(month_path(bridge).with_name("1.json"))
    with pytest.raises(ValueError, match="filename"):
        bridge.validate(bridge.deploy_path)


def test_rich_meal_slot_and_public_source_contract(bridge):
    bridge.build()
    month = read_json(month_path(bridge))
    slot = month["days"]["2026-01-01"]["breakfast"]
    assert len(slot["menu_items"]) == 2 and isinstance(slot, dict)
    assert set(slot["source"]) == SOURCE_FIELDS
    assert slot["source"] == month["sources"][0]


def test_manifest_stats_reconciled(bridge):
    result = bridge.build()
    stats = read_json(bridge.deploy_path / "manifest.json")["stats"]
    assert stats == {"total_institutions": 55, "collected_institutions": 1, "structured_documents": 1,
                     "total_meal_records": 6, "institution_month_files": 2,
                     "last_updated": "2026-10-01T17:00:00+09:00", "data_scope": "excel_ready_only"}
    assert result["status"] == "PASS"


def test_build_leaves_active_pointer_and_immutable_run_unchanged(bridge):
    pointer, run, _ = bridge.active_run()
    digest = tree_digest(run)
    before = (bridge.settings.production_root / "current.json").read_bytes()
    bridge.build()
    assert tree_digest(run) == digest
    assert (bridge.settings.production_root / "current.json").read_bytes() == before
    assert bridge.active_run()[0] == pointer


@pytest.mark.parametrize("change", [
    lambda m: m.update(is_mock_fixture=True),
    lambda m: m["sources"][0].update(local_path="raw/private.xlsx"),
    lambda m: m["sources"][0].update(original_filename="C:\\private\\meal.xlsx"),
    lambda m: m["sources"][0].update(post_url="file:///private.xlsx"),
    lambda m: m["days"]["2026-01-01"].update(breakfast=[]),
    lambda m: m["days"]["2026-01-01"]["breakfast"].update(source_document_id="missing"),
    lambda m: m.update(month=3),
])
def test_invalid_public_contract_rejected(bridge, change):
    bridge.build()
    mutate(month_path(bridge), change)
    with pytest.raises((ValueError, TypeError)):
        bridge.validate(bridge.deploy_path)


def test_menu_count_reconciliation(bridge):
    bridge.build()
    month_path(bridge).unlink()
    with pytest.raises(ValueError, match="month files"):
        bridge.validate(bridge.deploy_path)


def test_active_dataset_version_reconciliation(bridge):
    bridge.build()
    mutate(bridge.deploy_path / "manifest.json", lambda m: m.update(dataset_version="old"))
    with pytest.raises(ValueError, match="version"):
        bridge.sync()


def test_unknown_availability_identity_rejected(bridge):
    bridge.build()
    mutate(bridge.deploy_path / "manifest.json", lambda m: m["institutions"][0].update(institution_id="unknown"))
    with pytest.raises(ValueError, match="identity"):
        bridge.validate(bridge.deploy_path)


def test_same_count_content_tamper_rejected(bridge):
    bridge.build()
    mutate(month_path(bridge), lambda m: m["days"]["2026-01-01"]["breakfast"]["menu_items"][0].update(name="fake"))
    with pytest.raises(ValueError, match="immutable"):
        bridge.validate(bridge.deploy_path)


def test_sync_whole_tree_isolates_and_preserves_mock(bridge):
    destination = bridge.settings.project_root / "web/public/web_data"
    atomic_json(destination / "manifest.json", {"is_mock_fixture": True})
    atomic_json(destination / "mock-only.json", {"is_mock_fixture": True})
    old_hash = tree_digest(destination)
    bridge.build()
    result = bridge.sync()
    assert result["status"] == "PASS" and tree_digest(destination) == tree_digest(bridge.deploy_path)
    fixture = bridge.settings.project_root / "web/tests/fixtures/web_data/w1"
    assert tree_digest(fixture) == old_hash
    assert not (destination / "mock-only.json").exists()
    assert Path(result["previous_web_data"]).is_relative_to(bridge.settings.project_root / "web/tests")
    assert len(list((destination / "menus").rglob("*.json"))) == 2


def test_invalid_sync_preserves_previous_bundle(bridge):
    bridge.build()
    bridge.sync()
    destination = bridge.settings.project_root / "web/public/web_data"
    old_hash = tree_digest(destination)
    mutate(month_path(bridge), lambda m: m.update(is_mock_fixture=True))
    with pytest.raises(ValueError, match="mock"):
        bridge.sync()
    assert tree_digest(destination) == old_hash


@pytest.mark.parametrize("failure_phase", ["move_old", "move_new", "validate_new"])
def test_directory_promotion_failure_rolls_back(bridge, monkeypatch, failure_phase):
    import production.web_bridge as module
    bridge.build()
    bridge.sync()
    destination = bridge.settings.project_root / "web/public/web_data"
    staged = destination.parent / ".web_data.staging-test"
    shutil.copytree(bridge.deploy_path, staged)
    old_hash = tree_digest(destination)
    original = module.os.replace
    fired = False
    def rename(source, target):
        nonlocal fired
        if not fired and ((failure_phase == "move_old" and Path(source) == destination) or
                          (failure_phase == "move_new" and Path(source) == staged)):
            fired = True
            raise OSError("injected rename failure")
        return original(source, target)
    monkeypatch.setattr(module.os, "replace", rename)
    def validator(path):
        if failure_phase == "validate_new" and path == destination:
            raise ValueError("injected validation failure")
        return bridge.validate(path)
    with pytest.raises((ValueError, OSError), match="injected"):
        promote_directory(staged, destination, validator)
    assert destination.exists() and tree_digest(destination) == old_hash


def test_crash_journal_restores_previous_directory(bridge):
    bridge.build()
    destination = bridge.deploy_path
    old_hash = tree_digest(destination)
    backup = destination.parent / ".web_data.previous-crash"
    destination.rename(backup)
    atomic_json(destination.parent / ".web_data.swap.json", {
        "destination": "web_data", "staged": ".web_data.staging-crash", "backup": backup.name,
        "backup_root": str(destination.parent.resolve())})
    recover_directory_swap(destination)
    assert tree_digest(destination) == old_hash


def test_cross_contract_fixtures_are_real_rich_subsets(bridge):
    bridge.build()
    result = bridge.build_fixtures()
    root = bridge.settings.project_root / "web/tests/fixtures/web_contract/web_data"
    assert result["institution_month_files"] == 2
    assert validate_web_bundle(root)["status"] == "PASS"
    for path in (root / "menus").rglob("*.json"):
        assert path.read_bytes() == (bridge.deploy_path / path.relative_to(root)).read_bytes()
    assert result["multi_item_meal_types"] == ["breakfast", "lunch", "dinner"]


def test_non_json_public_file_rejected(bridge):
    bridge.build()
    (bridge.deploy_path / "private.txt").write_text("not public", encoding="utf-8")
    with pytest.raises(ValueError, match="non-JSON"):
        bridge.validate(bridge.deploy_path)
