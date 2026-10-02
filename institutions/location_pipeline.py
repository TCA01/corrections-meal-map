from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import shutil
import uuid

from config.settings import Settings
from production.io import atomic_json
from production.validation import read_json
from production.web_bridge import WebDataBridge, tree_digest, promote_directory, recover_directory_swap
from operations.state import RunLock
from .geocoding import CachedLocationClient, OfficialLocationAdapter, KakaoAddressGeocoder, timestamp
from .location_validation import validate_location, duplicate_coordinates, province


def recover_location_publication(settings, bridge):
    root = settings.institutions_path.parent
    journal = root / "location_transaction.json"
    if not journal.exists():
        return
    value = read_json(journal)
    backup = (root / value["backup"]).resolve()
    if not backup.is_relative_to((root / "location_backups").resolve()):
        raise ValueError("unsafe location recovery path")
    if read_json(settings.production_root / "current.json") != value["current_pointer"]:
        raise ValueError("production changed during interrupted location publication; operator review required")
    atomic_json(settings.institutions_path, read_json(backup / "institutions.json"))
    destinations = [("deploy", bridge.deploy_path, bridge.deploy_path.parent),
                    ("frontend", settings.project_root / "web/public/web_data",
                     settings.project_root / "web/tests/fixtures/web_data/backups")]
    for name, destination, backup_root in destinations:
        recover_directory_swap(destination, backup_root=backup_root)
        stage = destination.parent / f".web_data.restore-location-{uuid.uuid4().hex}"
        shutil.copytree(backup / name, stage)
        promote_directory(stage, destination, bridge.validate, backup_root=backup_root)
    journal.unlink()


def apply_location_master(settings, bridge, master, updated):
    """Existing bridge + durable cross-master/bundle rollback; does not touch current."""
    root = settings.institutions_path.parent
    backup = root / "location_backups" / uuid.uuid4().hex
    atomic_json(backup / "institutions.json", master)
    shutil.copytree(bridge.deploy_path, backup / "deploy")
    shutil.copytree(settings.project_root / "web/public/web_data", backup / "frontend")
    journal = root / "location_transaction.json"
    atomic_json(journal, {"backup": backup.relative_to(root).as_posix(),
                          "current_pointer": read_json(settings.production_root / "current.json")})
    try:
        atomic_json(settings.institutions_path, updated)
        bridge.build()
        bridge.sync()
        bridge.validate(bridge.deploy_path)
        bridge.validate(settings.project_root / "web/public/web_data")
        for name, destination in [("deploy", bridge.deploy_path),
                                  ("frontend", settings.project_root / "web/public/web_data")]:
            if tree_digest(backup / name / "menus") != tree_digest(destination / "menus") or (
                (backup / name / "manifest.json").read_bytes() != (destination / "manifest.json").read_bytes()):
                raise ValueError("location publication changed menus or manifest")
        journal.unlink()
    except BaseException:
        recover_location_publication(settings, bridge)
        raise


def enrich_locations(master, official, links, geocoder=None):
    updated, audit = deepcopy(master), []
    for index, item in enumerate(updated):
        print(f"Location {index + 1}/{len(updated)}: {item['canonical_name']}", flush=True)
        row = {"institution_id": item["institution_id"], "canonical_name": item["canonical_name"],
               "official_address": item["address"], "latitude": None, "longitude": None,
               "status": "UNRESOLVED", "location_confidence": "none", "location_source": None,
               "location_source_url": None, "provider": None, "geocoded_at": timestamp(),
               "geocoding_query": item["address"], "returned_address": None, "candidates": [], "validation": {}}
        candidates = []
        try:
            home = links.get(item["institution_id"])
            candidate, evidence = official.locate(item, home) if home else (None, {"reason": "OFFICIAL_HOME_NOT_FOUND"})
            row["official_lookup"] = evidence
            if candidate:
                candidates.append(candidate)
            elif geocoder:
                candidates, evidence = geocoder.locate(item)
                row["geocoder_lookup"] = evidence
        except Exception as error:
            row["lookup_error_type"] = type(error).__name__
        for candidate in candidates:
            candidate["validation"] = validate_location(item, candidate)
        row["candidates"] = candidates
        # Multiple results are ambiguous even if one happens to pass a coarse check.
        if len(candidates) == 1:
            candidate = candidates[0]
            row.update(location_source=candidate["provider"], location_source_url=candidate["source_url"],
                       provider=candidate["provider"], returned_address=candidate["returned_address"],
                       geocoding_query=candidate["query"], validation=candidate["validation"])
            if candidate["validation"]["status"] == "PASS":
                row.update(latitude=float(candidate["latitude"]), longitude=float(candidate["longitude"]),
                           status="VERIFIED" if candidate["official"] else "GEOCODED",
                           location_confidence="high" if candidate["official"] else "address_match")
            else:
                row["status"] = "REVIEW"
        elif candidates:
            row.update(status="REVIEW", validation={"status": "REVIEW", "issues": ["MULTIPLE_CANDIDATES"]})
        item["latitude"], item["longitude"] = row["latitude"], row["longitude"]
        audit.append(row)
    duplicates = duplicate_coordinates(audit)
    # Identical physical addresses may intentionally share a marker; different
    # addresses sharing a point must be withheld, never jittered apart.
    by_id = {r["institution_id"]: r for r in audit}
    for group in duplicates:
        if not group["same_official_road_address"]:
            for institution_id in group["institution_ids"]:
                row = by_id[institution_id]
                row.update(status="REVIEW", latitude=None, longitude=None, location_confidence="ambiguous")
                row["validation"]["issues"].append("DUPLICATE_COORDINATE_DIFFERENT_ADDRESS")
                row["validation"]["status"] = "REVIEW"
                item = next(i for i in updated if i["institution_id"] == institution_id)
                item["latitude"] = item["longitude"] = None
    return updated, audit, duplicates


def location_report(audit, duplicates, ready_ids):
    approved = [row for row in audit if row["status"] in {"VERIFIED", "GEOCODED"}]
    states = Counter(row["status"] for row in audit)
    regions = defaultdict(list)
    for row in approved:
        regions[province(row["official_address"])].append(row)
    return {"generated_at": timestamp(), "master_institutions": len(audit),
            "location_results": {key.lower(): states[key] for key in ("VERIFIED", "GEOCODED", "REVIEW", "UNRESOLVED")},
            "map_ready": len(approved), "ready_data_institutions": len(ready_ids),
            "ready_data_institutions_with_coordinates": len({r["institution_id"] for r in approved} & set(ready_ids)),
            "providers": dict(Counter(r["provider"] for r in approved)), "duplicate_coordinates": duplicates,
            "geographic_sanity": {
                "status": "PASS" if all(row["validation"]["status"] == "PASS" for row in approved) else "FAIL",
                "min_latitude": min((r["latitude"] for r in approved), default=None),
                "max_latitude": max((r["latitude"] for r in approved), default=None),
                "min_longitude": min((r["longitude"] for r in approved), default=None),
                "max_longitude": max((r["longitude"] for r in approved), default=None),
                "regions": {key: {"min_latitude": min(r["latitude"] for r in rows),
                                  "max_latitude": max(r["latitude"] for r in rows),
                                  "min_longitude": min(r["longitude"] for r in rows),
                                  "max_longitude": max(r["longitude"] for r in rows)} for key, rows in regions.items()},
                "land_polygon_verified": False}}


def run_location_enrichment(settings=None, *, apply=False, allow_kakao=False):
    settings = settings or Settings()
    root = settings.institutions_path.parent
    with RunLock(settings.project_root / "data/ops/update.lock", settings.ops_lock_stale_seconds):
        bridge = WebDataBridge(settings)
        recover_location_publication(settings, bridge)
        master = read_json(settings.institutions_path)
        if len(master) != 55 or len({i["institution_id"] for i in master}) != 55:
            raise ValueError("expected unchanged 55-institution master")
        pointer, run, production = bridge.active_run()
        before = {"current": pointer, "run_sha256": tree_digest(run),
                  "menus_sha256": tree_digest(run / "web_data/menus"),
                  "deploy_menus_sha256": tree_digest(bridge.deploy_path / "menus"),
                  "frontend_menus_sha256": tree_digest(settings.project_root / "web/public/web_data/menus"),
                  "deploy_manifest": (bridge.deploy_path / "manifest.json").read_bytes(),
                  "frontend_manifest": (settings.project_root / "web/public/web_data/manifest.json").read_bytes()}
        bridge.validate(bridge.deploy_path)
        bridge.validate(settings.project_root / "web/public/web_data")
        client = CachedLocationClient(root / "location_raw")
        official = OfficialLocationAdapter(client)
        directory = client.get(official.directory_url)
        links = official.institution_links(directory["payload"], master)
        geocoder = KakaoAddressGeocoder(client) if allow_kakao else None
        updated, audit, duplicates = enrich_locations(master, official, links, geocoder)
        ready_ids = {row["institution_id"] for row in read_json(run / "web_data/institutions.json")}
        report = location_report(audit, duplicates, ready_ids)
        for old, new in zip(master, updated):
            if {k: v for k, v in old.items() if k not in {"latitude", "longitude"}} != {k: v for k, v in new.items() if k not in {"latitude", "longitude"}}:
                raise ValueError("non-coordinate master change")
        atomic_json(root / "location_audit.json", audit)
        atomic_json(root / "location_review.json", [r for r in audit if r["status"] in {"REVIEW", "UNRESOLVED"}])
        atomic_json(root / "institutions_location_candidate.json", updated)
        report.update(applied=False, public_institutions="NOT_APPLIED", web_sync="NOT_APPLIED")
        if apply:
            # Retain the exact previous master as recovery/audit evidence.
            if not (root / "institutions_before_locations.json").exists():
                atomic_json(root / "institutions_before_locations.json", master)
            apply_location_master(settings, bridge, master, updated)
            report.update(applied=True, public_institutions="PASS", web_sync="PASS")
        unchanged = (read_json(settings.production_root / "current.json") == before["current"]
                     and tree_digest(run) == before["run_sha256"]
                     and tree_digest(run / "web_data/menus") == before["menus_sha256"]
                     and tree_digest(bridge.deploy_path / "menus") == before["deploy_menus_sha256"]
                     and tree_digest(settings.project_root / "web/public/web_data/menus") == before["frontend_menus_sha256"]
                     and (bridge.deploy_path / "manifest.json").read_bytes() == before["deploy_manifest"]
                     and (settings.project_root / "web/public/web_data/manifest.json").read_bytes() == before["frontend_manifest"])
        report.update(menu_data_unchanged="PASS" if unchanged else "FAIL", dataset_version=pointer["dataset_version"],
                      ready_documents=production["documents"]["ready"], meal_slots=production["records"]["production_ready"],
                      month_files=production["web_data"]["institution_month_files"], menus_sha256=before["menus_sha256"])
        atomic_json(root / "location_report.json", report)
        if not unchanged:
            raise ValueError("location operation changed meal publication data")
        return report
