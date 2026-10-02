from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .validation import MEAL_TYPES, read_json, reject_local_paths, validate_public_source

SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "3B.1"
MASTER_FIELDS = {"institution_id", "name", "short_name", "type", "address", "postal_code", "phone",
                 "latitude", "longitude", "source_url", "active"}
SOURCE_FIELDS = {"document_id", "post_id", "attachment_id", "post_url", "download_url",
                 "original_filename", "published_date"}


def month_filename(month: int) -> str:
    if type(month) is not int or not 1 <= month <= 12:
        raise ValueError("month must be an integer from 1 to 12")
    return f"{month:02d}.json"


def validate_public_json(value: Any) -> None:
    reject_local_paths(value)
    if isinstance(value, dict):
        if value.get("is_mock_fixture") is True:
            raise ValueError("mock fixture in production bundle")
        for nested in value.values():
            validate_public_json(nested)
    elif isinstance(value, list):
        for nested in value:
            validate_public_json(nested)
    elif isinstance(value, str) and (re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("file://", "\\\\", "data/raw/", "data/samples/"))):
        raise ValueError("local storage path in public JSON")


def validate_source(source: dict[str, Any]) -> None:
    if set(source) != SOURCE_FIELDS:
        raise ValueError("public source fields differ from canonical contract")
    validate_public_source(source)
    date.fromisoformat(source["published_date"])
    if source["document_id"] != f"{source['post_id']}-{source['attachment_id']}":
        raise ValueError("source document identity mismatch")


def validate_web_bundle(root: Path, *, expected_version: str | None = None,
                        expected_master_count: int = 55, report: dict[str, Any] | None = None) -> dict[str, Any]:
    entries = list(root.rglob("*"))
    if root.is_symlink() or any(p.is_symlink() for p in entries):
        raise ValueError("symlink in web bundle")
    if any(p.is_file() and p.suffix != ".json" for p in entries):
        raise ValueError("unexpected non-JSON public file")
    paths = [p for p in entries if p.is_file()]
    for path in paths:
        if path.is_symlink():
            raise ValueError("symlink in web bundle")
        validate_public_json(read_json(path))
    master = read_json(root / "institutions.json")
    manifest = read_json(root / "manifest.json")
    if not isinstance(master, list) or len(master) != expected_master_count:
        raise ValueError("institution master count mismatch")
    ids = set()
    coordinates = 0
    for institution in master:
        if set(institution) != MASTER_FIELDS or not institution["institution_id"] or not institution["name"]:
            raise ValueError("institution master schema mismatch")
        if institution["institution_id"] in ids:
            raise ValueError("duplicate institution master identity")
        ids.add(institution["institution_id"])
        if any(not isinstance(institution[field], str) for field in ("institution_id", "name", "type", "address")):
            raise ValueError("invalid institution text field")
        if type(institution["active"]) is not bool:
            raise ValueError("active must be boolean")
        for field in ("postal_code", "phone", "short_name"):
            if institution[field] is not None and not isinstance(institution[field], str):
                raise ValueError("invalid nullable institution text field")
        lat, lon = institution["latitude"], institution["longitude"]
        if (lat is None) != (lon is None):
            raise ValueError("coordinate pair must both be null or numeric")
        if lat is not None:
            if type(lat) not in (int, float) or type(lon) not in (int, float) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError("invalid coordinates")
            coordinates += 1
        source_url = urlparse(institution["source_url"])
        if source_url.scheme not in {"http", "https"} or not source_url.netloc:
            raise ValueError("invalid institution source URL")
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("web_contract_version") != CONTRACT_VERSION:
        raise ValueError("web contract version mismatch")
    if expected_version is not None and manifest.get("dataset_version") != expected_version:
        raise ValueError("active dataset version mismatch")
    datetime.fromisoformat(manifest["generated_at"])
    expected_months = set()
    availability_ids = set()
    for row in manifest["institutions"]:
        if set(row) != {"institution_id", "available_years"} or row["institution_id"] not in ids or row["institution_id"] in availability_ids:
            raise ValueError("availability identity/schema mismatch")
        availability_ids.add(row["institution_id"])
        if not row["available_years"]:
            raise ValueError("empty institution availability")
        for year, months in row["available_years"].items():
            if not re.fullmatch(r"\d{4}", year) or not months or months != sorted(set(months)):
                raise ValueError("invalid availability year/month list")
            for month in months:
                expected_months.add((row["institution_id"], int(year), month))
                month_filename(month)
    actual_months = set()
    meal_count = 0
    source_documents = set()
    for path in (root / "menus").rglob("*.json"):
        value = read_json(path)
        key = (value.get("institution_id"), value.get("year"), value.get("month"))
        if value.get("schema_version") != SCHEMA_VERSION or key[0] not in ids or type(key[1]) is not int:
            raise ValueError("month schema/identity mismatch")
        if path.relative_to(root).as_posix() != f"menus/{key[0]}/{key[1]}/{month_filename(key[2])}":
            raise ValueError("month filename/identity mismatch")
        actual_months.add(key)
        sources = {}
        for source in value["sources"]:
            validate_source(source)
            if source["document_id"] in sources:
                raise ValueError("duplicate month source")
            sources[source["document_id"]] = source
        used_sources = set()
        if not value["days"]:
            raise ValueError("empty production month")
        for meal_date, meals in value["days"].items():
            parsed = date.fromisoformat(meal_date)
            if (parsed.year, parsed.month) != key[1:] or not meals or not set(meals) <= MEAL_TYPES:
                raise ValueError("invalid month day/meal keys")
            for slot in meals.values():
                if not isinstance(slot, dict) or set(slot) != {"menu_items", "source_document_id", "source_document_ids", "source"}:
                    raise ValueError("meal slot must use rich object schema")
                items = slot["menu_items"]
                if not isinstance(items, list) or not items or any(set(item) != {"name", "raw_text"} or not isinstance(item["name"], str) or not item["name"].strip() or not isinstance(item["raw_text"], str) for item in items):
                    raise ValueError("invalid menu_items array")
                primary = slot["source_document_id"]
                references = slot["source_document_ids"]
                if not isinstance(references, list) or not references or len(references) != len(set(references)) or primary not in references or not set(references) <= sources.keys():
                    raise ValueError("unlinked source_document_id")
                if slot["source"] != sources[primary]:
                    raise ValueError("inline source differs from source list")
                used_sources.update(references)
                meal_count += 1
        if used_sources != set(sources):
            raise ValueError("unreferenced month source")
        source_documents.update(used_sources)
    if expected_months != actual_months:
        raise ValueError("manifest and month files disagree")
    expected_paths = {"manifest.json", "institutions.json"} | {
        f"menus/{i}/{year}/{month_filename(month)}" for i, year, month in expected_months
    }
    if {p.relative_to(root).as_posix() for p in paths} != expected_paths:
        raise ValueError("unexpected public JSON files")
    stats = manifest["stats"]
    calculated = {"total_institutions": len(ids), "collected_institutions": len(availability_ids),
                  "structured_documents": len(source_documents), "total_meal_records": meal_count,
                  "institution_month_files": len(actual_months), "last_updated": manifest["generated_at"],
                  "data_scope": "excel_ready_only"}
    if stats != calculated:
        raise ValueError("manifest stats disagree with actual bundle")
    if report is not None:
        if report["run_metadata"]["dataset_version"] != manifest["dataset_version"] or report["documents"]["ready"] != len(source_documents) or report["records"]["production_ready"] != meal_count or report["web_data"]["institution_month_files"] != len(actual_months):
            raise ValueError("bundle disagrees with active production report")
    return {"status": "PASS", "dataset_version": manifest["dataset_version"], **calculated,
            "with_coordinates": coordinates, "without_coordinates": len(ids) - coordinates}
