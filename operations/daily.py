from __future__ import annotations

import uuid
import re
from collections import Counter
from dataclasses import replace
from datetime import datetime

from collector.crawler import CorrectionsCrawler
from config.settings import Settings
from institutions.master import InstitutionMaster
from production.io import atomic_json, read_jsonl
from .candidates import candidate_manifest, seed_ops_catalog
from .publication import IncrementalPublisher, read_documents, merge_ready, month_keys
from .registry import ParserRegistry, detect_format
from .state import RunLock, ReviewQueue, load, now


EXIT_CODES = {"SUCCESS": 0, "NO_CHANGES": 0, "PARTIAL": 1, "FATAL": 2, "LOCKED": 3}


class DailyUpdater:
    def __init__(self, settings=None, *, collector=None, registry=None):
        self.settings = settings or Settings()
        self.root = self.settings.project_root / "data/ops"
        self.collector = collector
        self.registry = registry or ParserRegistry(self.settings.project_root)

    def run(self, *, refresh_recent=None, dry_run=False):
        # Lock failures do not race-write the running owner's shared report/health.
        with RunLock(self.root / "update.lock", self.settings.ops_lock_stale_seconds):
            return self._run(refresh_recent=refresh_recent, dry_run=dry_run)

    def _run(self, *, refresh_recent, dry_run):
        run_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z") + "-ops-" + uuid.uuid4().hex[:8]
        run_root = self.root / "runs" / run_id
        run_root.mkdir(parents=True)
        atomic_json(run_root / "candidates.json", [])
        previous_health = load(self.root / "health.json", {})
        report = {"run_id": run_id, "started_at": now(), "finished_at": None, "status": "FATAL", "dry_run": dry_run,
                  "site": {"posts_checked": 0, "new_posts": 0, "changed_posts": 0},
                  "attachments": {"new": 0, "changed": 0, "unchanged": 0, "download_failed": 0},
                  "processing": {"auto_ready": 0, "review": 0, "failed": 0, "unsupported": 0},
                  "publication": {"published": False, "dataset_version": None, "months_added": 0,
                                  "months_updated": 0, "touched_months": []}}
        queue = ReviewQueue(self.root / "review_queue.json")
        processed_path = self.root / "processed_sources.json"
        processed = load(processed_path, {})
        drift = load(self.root / "parser_drift.json", {})
        try:
            master = InstitutionMaster.load(self.settings.institutions_path)
            publisher = IncrementalPublisher(self.settings, self.root, len(master.institutions))
            publisher.recover()
            pointer, base_run, base_report = publisher.bridge.active_run()
            publisher.expected_pointer = pointer
            report["publication"]["dataset_version"] = pointer["dataset_version"]
            publisher.pipeline._validate_staging(base_run, base_report)
            # Existing served bundle, when present, must agree with the active READY base.
            for _, destination, _ in publisher.destinations():
                if destination.exists():
                    publisher.bridge.validate(destination)
            base_docs = read_documents(base_run)
            for document in base_docs:
                if document["route"] == "ready":
                    families = [p.get("detected_layout_family") for p in document["result"].get("layout_profiles", [])]
                    drift.setdefault(f"{document['document_id']}:{document['manifest'].get('sha256')}",
                                     families[0] if families else "undetected")
            baseline = {d["document_id"]: {**d["manifest"], "detected_format": d["result"].get("detected_format")}
                        for d in base_docs}
            baseline.update(processed)
            collector = self.collector
            if collector is None:
                cfg = replace(self.settings, catalog_path=self.root / "catalog/posts.jsonl",
                              raw_root=self.root / "raw", failures_path=self.root / "failures.jsonl")
                seed_ops_catalog(self.settings, cfg.catalog_path, [d["manifest"] for d in base_docs])
                collector = CorrectionsCrawler(cfg)
                # Discovery history identifies existing posts/attachments, but only
                # production or processed outcomes may declare a SHA processed.
                # A dry-run download must not make a later real run skip parsing.
                for post in read_jsonl(cfg.catalog_path):
                    for attachment in post["attachments"]:
                        key = f"{post['post_id']}-{attachment['attachment_id']}"
                        baseline.setdefault(key, {"sha256": None})
            recent = self.settings.ops_refresh_recent if refresh_recent is None else refresh_recent
            if recent < 1:
                raise ValueError("refresh_recent must be positive")
            result = collector.collect(latest_only=True, refresh_recent=recent)
            report["site"]["posts_checked"] = result.posts_checked if result.posts_checked is not None else len(result.posts)
            report["site"]["failure_count"] = result.failure_count
            if result.status == "fatal":
                report["fatal_reason"] = "INITIAL_SITE_ACCESS_FAILED"
                return self.finish(report, queue, previous_health, run_root)
            candidates = candidate_manifest(result.posts, baseline, master)
            report["site"]["new_posts"] = len({c["post_id"] for c in candidates if c["change_type"] == "NEW_POST"})
            report["site"]["changed_posts"] = len({c["post_id"] for c in candidates if c["change_type"] == "ATTACHMENT_CHANGED"})
            ready = []
            pending_processed = {}
            for item in candidates:
                change = item["change_type"]
                report["attachments"]["new" if change.startswith("NEW_") else
                                      "unchanged" if change == "UNCHANGED" else "changed"] += 1
                if item["download_status"] == "failed":
                    report["attachments"]["download_failed"] += 1
                    queue.add(item, "DOWNLOAD_FAILED", "Attachment refresh could not be downloaded; previous source retained")
                    if change == "ATTACHMENT_CHANGED":
                        queue.add(item, "SOURCE_CHANGED_REVIEW_REQUIRED", "Refresh failed; previous READY source retained")
                    continue
                if change == "UNCHANGED":
                    item["detected_format"] = baseline[item["document_id"]].get("detected_format")
                    for review in queue.items:
                        if (review["post_id"], review["attachment_id"]) == (item["post_id"], item["attachment_id"]) and review["status"] == "OPEN":
                            review["last_seen"] = now()
                    continue
                try:
                    from production.io import verified_file
                    if verified_file(self.settings.project_root, item):
                        item["detected_format"] = detect_format(self.settings.project_root / item["local_path"])
                except Exception:
                    item["detected_format"] = "unknown"
                item["production_support"] = ("SUPPORTED" if item["detected_format"] in self.registry.handlers
                                              else "UNSUPPORTED_FOR_PRODUCTION" if item["detected_format"] not in {None, "unknown"}
                                              else "INVALID_OR_UNKNOWN")
                if item["document_role"] in {"staff", "supplementary", "other"}:
                    item["outcome"] = "OUT_OF_SCOPE"
                    pending_processed[item["document_id"]] = item
                    continue
                if not item["institution_id"]:
                    route, parsed, reasons = "review", {"production_support": item["production_support"]}, ["UNRESOLVED_INSTITUTION"]
                elif item["document_role"] not in {"inmate", "mixed"}:
                    route, parsed, reasons = "review", {"production_support": item["production_support"]}, ["AMBIGUOUS_DOCUMENT_ROLE"]
                else:
                    route, parsed, reasons = self.registry.process(item)
                item["outcome"] = "AUTO_READY" if route == "ready" else route.upper()
                atomic_json(run_root / "documents" / f"{item['document_id']}.json", parsed)
                family = item.get("layout_family") or ("unknown" if "NEW_LAYOUT" in reasons else "undetected")
                drift[f"{item['document_id']}:{item.get('sha256')}"] = family
                if route == "ready":
                    item["parser_status"] = "parsed"
                    ready.append({"document_id": item["document_id"], "manifest": item, "result": parsed, "route": "ready"})
                else:
                    report["processing"][route] += 1
                    for reason in reasons:
                        queue.add(item, reason, "Document quarantined; previous public data retained")
                    if change == "ATTACHMENT_CHANGED":
                        queue.add(item, "SOURCE_CHANGED_REVIEW_REQUIRED", "New source version not READY; old READY version retained")
                    pending_processed[item["document_id"]] = item
            merged, accepted, rejected = merge_ready(base_docs, ready)
            for doc in rejected:
                item = doc["manifest"]
                item["outcome"] = "REVIEW"
                queue.add(item, "DATA_CONFLICT", "Different content for an existing institution/date/meal; no overwrite")
                if item["change_type"] == "ATTACHMENT_CHANGED":
                    queue.add(item, "SOURCE_CHANGED_REVIEW_REQUIRED", "Changed source conflicts; prior READY retained")
                pending_processed[item["document_id"]] = item
                report["processing"]["review"] += 1
            report["processing"]["auto_ready"] = len(accepted)
            atomic_json(run_root / "candidates.json", candidates)
            if accepted:
                stage, public, production_report, touched = publisher.prepare(base_run, base_docs, merged, accepted, run_id)
                old_months = month_keys(base_docs)
                new_months = month_keys(merged)
                report["publication"].update(months_added=len(new_months - old_months),
                                             months_updated=len(touched & old_months & new_months),
                                             touched_months=[list(k) for k in sorted(touched)])
                if not dry_run:
                    publisher.publish(stage, public, production_report, run_id, run_root)
                    report["publication"].update(published=True, dataset_version=run_id)
                    for doc in accepted:
                        queue.resolve_source(doc["manifest"])
                        pending_processed[doc["document_id"]] = doc["manifest"]
            partial = result.status == "partial" or any(report["processing"][k] for k in ("review", "failed", "unsupported")) or report["attachments"]["download_failed"]
            report["status"] = "PARTIAL" if partial else "SUCCESS" if accepted else "NO_CHANGES"
            if not dry_run:
                processed.update(pending_processed)
                atomic_json(processed_path, processed)
                atomic_json(self.root / "parser_drift.json", drift)
            report["parser_drift"] = dict(Counter(drift.values()))
        except Exception as error:
            # Diagnostic class only: health/report never include exception text with local paths.
            report.update(status="FATAL", fatal_reason="OPERATION_VALIDATION_OR_PUBLICATION_FAILED",
                          error_type=type(error).__name__)
        return self.finish(report, queue, previous_health, run_root)

    def finish(self, report, queue, previous_health, run_root):
        queue.save()
        report["finished_at"] = now()
        opened = [i for i in queue.items if i["status"] == "OPEN"]
        new_layouts = sum(i["reason_code"] == "NEW_LAYOUT" for i in opened)
        report["review"] = {"open_total": len(opened), "new_review_items": queue.new_count, "new_layout_count": new_layouts}
        successful = previous_health.get("last_successful_update")
        if (report["status"] in {"SUCCESS", "NO_CHANGES"} or report["publication"]["published"]) and not report["dry_run"]:
            successful = report["finished_at"]
        elapsed = (datetime.now().astimezone() - datetime.fromisoformat(successful)).days if successful else None
        try:
            pointer = load(self.settings.production_root / "current.json", {})
        except (ValueError, OSError):
            pointer = {}
        version = pointer.get("dataset_version") if isinstance(pointer, dict) else None
        if version is not None and not re.fullmatch(r"[A-Za-z0-9+_.-]+", str(version)):
            version = None
        report["publication"]["dataset_version"] = version
        health = {"last_run": report["finished_at"], "last_successful_update": successful,
                  "current_dataset_version": version,
                  "status": "error" if report["status"] == "FATAL" else "healthy",
                  "last_run_status": report["status"], "open_review_items": len(opened),
                  "new_layout_items": new_layouts, "days_since_success": elapsed,
                  "stale": elapsed is None or elapsed >= 7}
        report["health"] = {"last_successful_update": successful, "current_dataset_version": version}
        report["exit_code"] = EXIT_CODES[report["status"]]
        atomic_json(run_root / "report.json", report)
        atomic_json(self.root / "latest_report.json", report)
        atomic_json(self.root / "health.json", health)
        return report
