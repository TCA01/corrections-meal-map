from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

MEAL_TYPES = {"breakfast", "lunch", "dinner"}
KNOWN_LAYOUTS = {"date_rows_meal_columns", "weekday_blocks_meal_columns", "meal_rows_weekday_columns"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_record(record: dict[str, Any], *, institution_id: str) -> None:
    if record.get("schema_version") != "1.0" or record.get("institution_id") != institution_id:
        raise ValueError("record schema/institution mismatch")
    date.fromisoformat(record["meal_date"])
    if record.get("meal_type") not in MEAL_TYPES or record.get("validation_status") != "valid":
        raise ValueError("invalid ready record meal/status")
    menus = record.get("menu_items")
    if not isinstance(menus, list) or not menus or any(not m.get("name", "").strip() for m in menus):
        raise ValueError("empty ready record menu")
    source = record.get("source") or {}
    if not all(source.get(key) for key in ("post_id", "attachment_id", "sheet", "cells")):
        raise ValueError("missing ready record provenance")
    if (record.get("parser") or {}).get("layout_family") not in KNOWN_LAYOUTS:
        raise ValueError("unknown layout in ready record")


def validate_public_source(source: dict[str, Any]) -> None:
    if not all(source.get(key) for key in ("document_id", "post_id", "attachment_id", "original_filename", "published_date")):
        raise ValueError("missing public source metadata")
    for key in ("post_url", "download_url"):
        url = urlparse(str(source.get(key) or ""))
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise ValueError(f"invalid public {key}")


def reject_local_paths(value: Any) -> None:
    if isinstance(value, dict):
        if {"local_path", "duplicate_of", "storage_root", "raw_path"} & set(value):
            raise ValueError("local storage metadata leaked into public JSON")
        for nested in value.values():
            reject_local_paths(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_local_paths(nested)


def validate_dataset(root: Path, report: dict[str, Any], canonical_ids: set[str]) -> dict[str, Any]:
    """Reconcile immutable run manifest, routed records, public sources and index."""
    manifest = [json.loads(line) for line in (root / "excel_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line]
    ids = {item["document_id"] for item in manifest}
    if len(ids) != len(manifest) or len(manifest) != report["documents"]["target"]:
        raise ValueError("manifest target/duplicate identity mismatch")
    expected_by_route = {route: {i["document_id"] for i in manifest if i["production_status"] == route}
                         for route in ("ready", "review", "failed")}
    ready_slots: dict[tuple[str, str, str], tuple[str, ...]] = {}
    ready_source_ids: dict[tuple[str, str, str], set[str]] = {}
    for route, expected in expected_by_route.items():
        files = list((root / route).glob("*.json"))
        if {p.stem for p in files} != expected or len(files) != report["documents"][route]:
            raise ValueError(f"{route} files disagree with run manifest/report")
        for path in files:
            document = read_json(path)
            if document["document_id"] != path.stem or document["production_status"] != route:
                raise ValueError("routed document identity mismatch")
            if route != "ready":
                continue
            institution_id = document.get("institution_id")
            if institution_id not in canonical_ids:
                raise ValueError("unknown institution in ready dataset")
            validate_public_source(document["source_metadata"])
            for record in document.get("records", []):
                validate_record(record, institution_id=institution_id)
                key = (institution_id, record["meal_date"], record["meal_type"])
                content = tuple(m["name"] for m in record["menu_items"])
                if key in ready_slots and ready_slots[key] != content:
                    raise ValueError("conflicting ready menu")
                ready_slots[key] = content
                ready_source_ids.setdefault(key, set()).add(path.stem)
    if sum(len(v) for v in expected_by_route.values()) != len(manifest):
        raise ValueError("unrouted manifest item")
    public_root = root / "web_data"
    index = read_json(public_root / "manifest.json")
    institutions = read_json(public_root / "institutions.json")
    if index.get("schema_version") != "1.0" or index.get("dataset_version") != report["run_metadata"]["dataset_version"]:
        raise ValueError("public manifest schema/version mismatch")
    if index.get("institutions") != institutions:
        raise ValueError("public institution indexes disagree")
    expected_months = {(row["institution_id"], int(year), int(month))
                       for row in institutions for year, months in row["available_years"].items() for month in months}
    actual_months = set()
    public_slots = {}
    for path in (public_root / "menus").rglob("*.json"):
        month = read_json(path)
        key = (month.get("institution_id"), month.get("year"), month.get("month"))
        if key[0] not in canonical_ids or month.get("schema_version") != "1.0":
            raise ValueError("public month schema/institution mismatch")
        if path.relative_to(public_root).as_posix() != f"menus/{key[0]}/{key[1]}/{key[2]:02d}.json":
            raise ValueError("public month filename mismatch")
        actual_months.add(key)
        sources = {s["document_id"]: s for s in month["sources"]}
        for source in sources.values():
            validate_public_source(source)
        for meal_date, meals in month["days"].items():
            parsed_date = date.fromisoformat(meal_date)
            if (parsed_date.year, parsed_date.month) != key[1:]:
                raise ValueError("public meal date outside month")
            for meal_type, meal in meals.items():
                slot = (key[0], meal_date, meal_type)
                if meal_type not in MEAL_TYPES or slot not in ready_slots:
                    raise ValueError("unexpected public meal")
                source_ids = set(meal.get("source_document_ids", [meal["source_document_id"]]))
                if source_ids != ready_source_ids[slot] or not source_ids <= sources.keys():
                    raise ValueError("public source references disagree with ready documents")
                if meal["source"] != sources.get(meal["source_document_id"]):
                    raise ValueError("public primary source mismatch")
                public_slots[slot] = tuple(m["name"] for m in meal["menu_items"])
    if actual_months != expected_months or public_slots != ready_slots:
        raise ValueError("public monthly projection/index disagree with ready records")
    if len(public_slots) != report["records"]["production_ready"]:
        raise ValueError("public unique meal count differs from report")
    for path in public_root.rglob("*.json"):
        reject_local_paths(read_json(path))
    return {"status": "PASS", "documents_checked": len(manifest), "monthly_files_checked": len(actual_months),
            "public_records_checked": len(public_slots)}
