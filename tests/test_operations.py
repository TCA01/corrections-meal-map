from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from copy import deepcopy
from pathlib import Path

import pytest

from collector.crawler import CollectionRunResult
from collector.models import Post, Attachment
from institutions.master import InstitutionMaster
from operations.candidates import candidate_manifest
from operations.daily import DailyUpdater
from operations.publication import IncrementalPublisher, read_documents, merge_ready
from operations.registry import ParserRegistry, detect_format
from operations.state import ReviewQueue, RunLock, RunLocked, load
from production.io import atomic_json
from production.web_bridge import WebDataBridge, tree_digest
from test_production import publish_one, ready_result


class FixtureCollector:
    def __init__(self, posts=(), status="success"):
        self.posts = posts
        self.status = status
        self.calls = []

    def collect(self, **kwargs):
        self.calls.append(kwargs)
        return CollectionRunResult(deepcopy(list(self.posts)), self.status, int(self.status != "success"))


@pytest.fixture
def base(tmp_path, monkeypatch):
    cfg, report, run = publish_one(tmp_path, monkeypatch)
    bridge = WebDataBridge(cfg, expected_master_count=1)
    bridge.build()
    bridge.sync()
    return cfg, report, run


def new_post(cfg, document_id="2-2", content=b"new", *, status="downloaded", role_name="수용자식단표.xlsx"):
    post_id, attachment_id = document_id.split("-")
    relative = f"raw/{document_id}-{hashlib.sha256(content).hexdigest()[:8]}.xlsx"
    path = cfg.project_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    item = Attachment(attachment_id, role_name, "xlsx", f"https://example.test/download/{attachment_id}",
                      sha256=hashlib.sha256(content).hexdigest() if status != "failed" else None,
                      file_size=len(content), local_path=relative if status != "failed" else None, status=status)
    return Post(post_id, "기관", "[기관] 2026년 2월 수용자 식단표", "2026-02-01",
                f"https://example.test/post/{post_id}", attachment_count=1, is_meal_plan=True,
                meal_year=2026, meal_month=2, attachments=[item])


def registry(cfg, monkeypatch, *, menu="국", month="02", failure=None):
    reg = ParserRegistry(cfg.project_root)
    monkeypatch.setattr("operations.registry.detect_format", lambda path: "xlsx")
    monkeypatch.setattr("operations.daily.detect_format", lambda path: "xlsx")
    def parse(item):
        result = ready_result(item["document_id"], menu=menu)
        result["records"][0]["meal_date"] = f"2026-{month}-01"
        if failure:
            result.update(status="FAIL", records=[], failures=[{"code": failure}])
        return result
    monkeypatch.setattr(reg.excel, "parse_sample", parse)
    monkeypatch.setattr(reg, "diagnose", lambda item: {"sheets": [{"sheet": "new", "actual_range": "A1:C10",
                                                                "merged_cell_count": 0}], "source_url": item["post_url"]})
    return reg


def updater(base, monkeypatch, posts=(), *, status="success", **kwargs):
    cfg, _, _ = base
    collector = FixtureCollector(posts, status)
    return DailyUpdater(cfg, collector=collector, registry=registry(cfg, monkeypatch, **kwargs)), collector


def snapshot(cfg):
    return ((cfg.production_root / "current.json").read_bytes(),
            tree_digest(cfg.production_root / "deploy/web_data"), tree_digest(cfg.project_root / "web/public/web_data"))


def test_candidate_changes(base):
    cfg, _, run = base
    master = InstitutionMaster.load(cfg.institutions_path)
    old = {d["document_id"]: d["manifest"] for d in read_documents(run)}
    same = new_post(cfg, "1-1", b"x")
    changed = new_post(cfg, "1-1")
    attachment = new_post(cfg, "1-2")
    new = new_post(cfg)
    assert candidate_manifest([same], old, master)[0]["change_type"] == "UNCHANGED"
    assert candidate_manifest([changed], old, master)[0]["change_type"] == "ATTACHMENT_CHANGED"
    assert candidate_manifest([attachment], old, master)[0]["change_type"] == "NEW_ATTACHMENT"
    assert candidate_manifest([new], old, master)[0]["change_type"] == "NEW_POST"
    old["2-2"] = {"sha256": None}
    assert candidate_manifest([new], old, master)[0]["change_type"] == "NEW_ATTACHMENT"


def test_registry_extensible(base):
    cfg, _, _ = base
    reg = ParserRegistry(cfg.project_root)
    handler = lambda item: ("ready", {}, [])
    reg.register("pdf", handler)
    assert reg.handlers["pdf"] is handler and set(reg.handlers) == {"xls", "xlsx", "pdf"}


def test_known_new_month_auto_ready(base, monkeypatch):
    cfg, _, run = base
    old_month = (run / "web_data/menus/I1/2026/01.json").read_bytes()
    before = tree_digest(run)
    update, collector = updater(base, monkeypatch, [new_post(cfg)])
    report = update.run()
    assert report["status"] == "SUCCESS", report
    assert report["processing"]["auto_ready"] == 1 and report["publication"]["published"]
    assert report["publication"]["months_added"] == 1
    pointer = load(cfg.production_root / "current.json")
    final = cfg.production_root / pointer["run_path"]
    assert (final / "web_data/menus/I1/2026/01.json").read_bytes() == old_month
    assert tree_digest(run) == before
    assert collector.calls == [{"latest_only": True, "refresh_recent": 10}]
    assert load(final / "web_data/menus/I1/2026/02.json")["days"]["2026-02-01"]["breakfast"]["menu_items"][0]["name"] == "국"


def test_new_layout_review_preserves_publication(base, monkeypatch):
    cfg, _, _ = base
    before = snapshot(cfg)
    update, _ = updater(base, monkeypatch, [new_post(cfg)], failure="UNSUPPORTED_LAYOUT")
    report = update.run()
    assert report["status"] == "PARTIAL" and report["review"]["new_layout_count"] == 1
    assert snapshot(cfg) == before
    diagnostic = load(update.root / "runs" / report["run_id"] / "documents/2-2.json")
    assert diagnostic["layout_diagnostics"]["sheets"][0]["actual_range"] == "A1:C10"


def test_corrupt_attachment_preserves(base, monkeypatch):
    cfg, _, _ = base
    before = snapshot(cfg)
    update, _ = updater(base, monkeypatch, [new_post(cfg)], failure="CORRUPT_WORKBOOK")
    report = update.run()
    assert report["processing"]["failed"] == 1 and report["status"] == "PARTIAL"
    assert snapshot(cfg) == before


def test_changed_valid_replaces_same_source(base, monkeypatch):
    cfg, _, old_run = base
    update, _ = updater(base, monkeypatch, [new_post(cfg, "1-1")], month="01", menu="죽")
    report = update.run()
    assert report["status"] == "SUCCESS" and report["attachments"]["changed"] == 1
    assert report["publication"]["months_updated"] == 1
    pointer = load(cfg.production_root / "current.json")
    month = load(cfg.production_root / pointer["run_path"] / "web_data/menus/I1/2026/01.json")
    assert month["days"]["2026-01-01"]["breakfast"]["menu_items"][0]["name"] == "죽"
    assert load(old_run / "web_data/menus/I1/2026/01.json")["days"]["2026-01-01"]["breakfast"]["menu_items"][0]["name"] == "밥"


def test_changed_invalid_preserves_old_ready(base, monkeypatch):
    cfg, _, _ = base
    before = snapshot(cfg)
    update, _ = updater(base, monkeypatch, [new_post(cfg, "1-1")], failure="CORRUPT_WORKBOOK")
    assert update.run()["status"] == "PARTIAL"
    assert snapshot(cfg) == before
    assert "SOURCE_CHANGED_REVIEW_REQUIRED" in {v["reason_code"] for v in load(update.root / "review_queue.json")}


def test_missing_source_never_deletes(base, monkeypatch):
    cfg, _, _ = base
    before = snapshot(cfg)
    update, _ = updater(base, monkeypatch)
    assert update.run()["status"] == "NO_CHANGES"
    assert snapshot(cfg) == before


def test_no_changes_never_parse(base, monkeypatch):
    cfg, _, _ = base
    update, _ = updater(base, monkeypatch, [new_post(cfg, "1-1", b"x")])
    monkeypatch.setattr(update.registry, "process", lambda item: pytest.fail("UNCHANGED must not parse"))
    before = snapshot(cfg)
    report = update.run()
    assert report["status"] == "NO_CHANGES" and report["attachments"]["unchanged"] == 1
    assert snapshot(cfg) == before


def test_duplicate_run_no_new_version(base, monkeypatch):
    cfg, _, _ = base
    post = new_post(cfg)
    update, _ = updater(base, monkeypatch, [post, post])
    first = update.run()
    assert first["status"] == "SUCCESS" and first["processing"]["auto_ready"] == 1
    version = first["publication"]["dataset_version"]
    monkeypatch.setattr(update.registry, "process", lambda item: pytest.fail("repeated run must not parse"))
    second = update.run()
    assert second["status"] == "NO_CHANGES" and second["publication"]["dataset_version"] == version
    assert second["review"]["new_review_items"] == 0


def test_review_dedup_and_second_run_no_parse(base, monkeypatch):
    cfg, _, _ = base
    update, _ = updater(base, monkeypatch, [new_post(cfg)], failure="UNSUPPORTED_LAYOUT")
    first = update.run()
    item = load(update.root / "review_queue.json")[0]
    monkeypatch.setattr(update.registry, "process", lambda _: pytest.fail("same quarantined SHA must not reparse"))
    second = update.run()
    assert first["review"]["new_review_items"] == 1 and second["review"]["new_review_items"] == 0
    assert second["status"] == "NO_CHANGES"
    assert load(update.root / "review_queue.json")[0]["review_id"] == item["review_id"]


def test_lock_rejects_parallel_run(tmp_path):
    path = tmp_path / "update.lock"
    with RunLock(path):
        with pytest.raises(RunLocked):
            with RunLock(path):
                pass
    assert not path.exists()


def test_stale_dead_lock_recovery(tmp_path, monkeypatch):
    path = tmp_path / "update.lock"
    atomic_json(path, {"pid": 123456, "host": socket.gethostname(), "created": time.time() - 99999, "token": "old"})
    monkeypatch.setattr("operations.state.process_alive", lambda pid: False)
    with RunLock(path, 1):
        assert load(path)["pid"] == os.getpid()
    assert len(list(tmp_path.glob("update.stale-*.json"))) == 1


def test_stale_live_lock_never_stolen(tmp_path):
    path = tmp_path / "update.lock"
    atomic_json(path, {"pid": os.getpid(), "host": socket.gethostname(), "created": time.time() - 99999, "token": "old"})
    with pytest.raises(RunLocked):
        with RunLock(path, 1):
            pass


@pytest.mark.parametrize("contents", [{"host": "remote", "pid": 1, "created": 0}, {}])
def test_remote_or_uncertain_lock_never_stolen(tmp_path, contents):
    path = tmp_path / "update.lock"
    atomic_json(path, contents)
    with pytest.raises(RunLocked):
        with RunLock(path, 1):
            pass


def test_partial_run_publishes_healthy_document(base, monkeypatch):
    cfg, _, _ = base
    update, _ = updater(base, monkeypatch, [new_post(cfg), new_post(cfg, "3-3", status="failed")], status="partial")
    report = update.run()
    assert report["status"] == "PARTIAL" and report["publication"]["published"]
    assert report["attachments"]["download_failed"] == 1 and report["processing"]["auto_ready"] == 1


def test_site_initial_failure_safe(base, monkeypatch):
    cfg, _, _ = base
    before = snapshot(cfg)
    update, _ = updater(base, monkeypatch, status="fatal")
    report = update.run()
    assert report["status"] == "FATAL" and report["exit_code"] == 2
    assert report["fatal_reason"] == "INITIAL_SITE_ACCESS_FAILED"
    assert load(update.root / "runs" / report["run_id"] / "candidates.json") == []
    assert snapshot(cfg) == before


def test_conflict_review_does_not_overwrite_base(base, monkeypatch):
    cfg, _, _ = base
    before = snapshot(cfg)
    update, _ = updater(base, monkeypatch, [new_post(cfg)], month="01", menu="죽")
    report = update.run()
    assert report["status"] == "PARTIAL" and report["processing"]["review"] == 1
    assert snapshot(cfg) == before
    assert load(update.root / "review_queue.json")[0]["reason_code"] == "DATA_CONFLICT"


def test_identical_content_dedup_keeps_source_provenance(base, monkeypatch):
    cfg, _, _ = base
    update, _ = updater(base, monkeypatch, [new_post(cfg)], month="01", menu="밥")
    report = update.run()
    assert report["status"] == "SUCCESS"
    pointer = load(cfg.production_root / "current.json")
    month = load(cfg.production_root / pointer["run_path"] / "web_data/menus/I1/2026/01.json")
    assert month["days"]["2026-01-01"]["breakfast"]["source_document_ids"] == ["1-1", "2-2"]


def test_report_and_health_have_required_safe_fields(base, monkeypatch):
    update, _ = updater(base, monkeypatch)
    report = update.run()
    assert set(report) >= {"run_id", "started_at", "finished_at", "status", "site", "attachments", "processing", "publication", "review", "health"}
    assert load(update.root / "latest_report.json") == report
    assert load(update.root / "runs" / report["run_id"] / "report.json") == report
    health = load(update.root / "health.json")
    assert health["status"] == "healthy" and health["days_since_success"] == 0
    assert "traceback" not in json.dumps(health) and "local_path" not in json.dumps(health)


def test_staging_validation_failure_preserves_every_public_tree(base, monkeypatch):
    cfg, _, _ = base
    before = snapshot(cfg)
    update, _ = updater(base, monkeypatch, [new_post(cfg)])
    monkeypatch.setattr(IncrementalPublisher, "export", lambda *args: (_ for _ in ()).throw(ValueError("contract invalid")))
    report = update.run()
    assert report["status"] == "FATAL" and not report["publication"]["published"]
    assert snapshot(cfg) == before


def test_sync_failure_rolls_back_pointer_and_deploy(base, monkeypatch):
    cfg, _, _ = base
    before = snapshot(cfg)
    update, _ = updater(base, monkeypatch, [new_post(cfg)])
    original = WebDataBridge.validate
    def fail_frontend(self, path):
        pointer = load(cfg.production_root / "current.json")
        if "-ops-" in pointer["dataset_version"] and path == cfg.project_root / "web/public/web_data":
            raise ValueError("simulated frontend validation failure")
        return original(self, path)
    monkeypatch.setattr(WebDataBridge, "validate", fail_frontend)
    report = update.run()
    assert report["status"] == "FATAL" and snapshot(cfg) == before


def test_dry_run_never_publishes_or_advances_processed(base, monkeypatch):
    cfg, _, _ = base
    before = snapshot(cfg)
    update, _ = updater(base, monkeypatch, [new_post(cfg)])
    report = update.run(dry_run=True)
    assert report["status"] == "SUCCESS" and not report["publication"]["published"]
    assert snapshot(cfg) == before and not (update.root / "processed_sources.json").exists()
    assert update.run()["status"] == "SUCCESS"


def test_corrupt_current_fatal_before_site_request(base, monkeypatch):
    cfg, _, run = base
    atomic_json(run / "web_data/menus/I1/2026/01.json", {})
    update, collector = updater(base, monkeypatch)
    report = update.run()
    assert report["status"] == "FATAL" and not collector.calls


def test_unsupported_pdf_is_not_corruption(base, monkeypatch):
    cfg, _, _ = base
    post = new_post(cfg, content=b"%PDF-1.7\n")
    reg = ParserRegistry(cfg.project_root)
    report = DailyUpdater(cfg, collector=FixtureCollector([post]), registry=reg).run()
    assert report["status"] == "PARTIAL" and report["processing"]["unsupported"] == 1
    assert report["processing"]["failed"] == 0


def test_role_ambiguity_review(base, monkeypatch):
    cfg, _, _ = base
    update, _ = updater(base, monkeypatch, [new_post(cfg, role_name="식단표.xlsx")])
    assert update.run()["processing"]["review"] == 1
    assert load(update.root / "review_queue.json")[0]["reason_code"] == "AMBIGUOUS_DOCUMENT_ROLE"


def test_unresolved_institution_review(base, monkeypatch):
    cfg, _, _ = base
    post = new_post(cfg)
    post.institution_name = "미상"
    post.title = "2026년 2월 식단"
    update, _ = updater(base, monkeypatch, [post])
    assert update.run()["processing"]["review"] == 1
    assert load(update.root / "review_queue.json")[0]["reason_code"] == "UNRESOLVED_INSTITUTION"


def test_parser_drift_unique_sha_counts(base, monkeypatch):
    cfg, _, _ = base
    update, _ = updater(base, monkeypatch, [new_post(cfg)])
    update.run()
    report = update.run()
    assert report["parser_drift"] == {"date_rows_meal_columns": 2}


def test_queue_ignored_stays_ignored_and_resolution(tmp_path):
    queue = ReviewQueue(tmp_path / "queue.json")
    item = {"post_id": "1", "attachment_id": "1", "filename": "x", "institution_id": "I1"}
    queue.add(item, "NEW_LAYOUT", "first")
    queue.items[0]["status"] = "IGNORED"
    queue.add(item, "NEW_LAYOUT", "repeat")
    assert queue.items[0]["status"] == "IGNORED" and queue.new_count == 1
    queue.add(item, "DATA_CONFLICT", "conflict")
    queue.resolve_source(item)
    assert queue.items[1]["status"] == "RESOLVED"


def test_restored_rejected_change_rechecks_other_new_sources(base):
    cfg, _, run = base
    docs = read_documents(run)
    changed = deepcopy(docs[0])
    changed["result"] = ready_result("1-1", menu="죽")
    another = deepcopy(changed)
    another.update(document_id="2-2", result=ready_result("2-2", menu="죽"))
    third = deepcopy(changed)
    third.update(document_id="3-3", result=ready_result("3-3", menu="국"))
    merged, accepted, rejected = merge_ready(docs, [changed, another, third])
    assert not accepted and len(rejected) == 3 and merged[0]["document_id"] == "1-1"


def test_actual_format_detection_signatures(tmp_path):
    import zipfile
    path = tmp_path / "misnamed.xls"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", "<x/>")
    assert detect_format(path) == "hwpx"
    path.write_bytes(b"broken")
    assert detect_format(path) == "unknown"


def test_new_layout_real_workbook_diagnostics(base):
    from openpyxl import Workbook
    cfg, _, _ = base
    post = new_post(cfg)
    item = post.attachments[0]
    path = cfg.project_root / item.local_path
    book = Workbook()
    book.active.append(["2026년 2월", "조식", "새로운 양식"])
    book.active["A2"] = "변경된 표"
    book.active.merge_cells("A2:C2")
    book.save(path)
    item.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    item.file_size = path.stat().st_size
    update = DailyUpdater(cfg, collector=FixtureCollector([post]))
    report = update.run()
    assert report["review"]["new_layout_count"] == 1, report
    diagnostic = load(update.root / "runs" / report["run_id"] / "documents/2-2.json")["layout_diagnostics"]
    assert diagnostic["sheets"][0]["meal_keywords"] == ["조식"]
    assert diagnostic["sheets"][0]["merged_cell_count"] == 1


def test_real_known_excel_auto_ready_incremental(base):
    """Use a real previously verified workbook, with no parser or detector stub."""
    import shutil
    from production.io import read_jsonl
    cfg, _, _ = base
    source_root = Path(__file__).resolve().parents[1]
    source = next(item for item in load(source_root / "tests/fixtures/menu_quality/manifest.json")
                  if item["production_status"] == "ready" and item["meal_year"] != 2026
                  and item["extension"] == "xlsx")
    post = new_post(cfg, "900-900", role_name="수용자식단표.xlsx")
    attachment = post.attachments[0]
    target = cfg.project_root / attachment.local_path
    shutil.copyfile(source_root / source["local_path"], target)
    attachment.sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
    attachment.file_size = target.stat().st_size
    post.meal_year = source["meal_year"]
    post.meal_month = source["meal_month"]
    post.title = f"[기관] {post.meal_year}년 {post.meal_month}월 수용자 식단표"
    report = DailyUpdater(cfg, collector=FixtureCollector([post])).run()
    assert report["status"] == "SUCCESS" and report["processing"]["auto_ready"] == 1, report


def test_publication_crash_journal_recovers_on_next_run(base, monkeypatch):
    import shutil
    cfg, _, _ = base
    update, _ = updater(base, monkeypatch)
    before = snapshot(cfg)
    backup = update.root / "runs/interrupted/publication_backup"
    shutil.copytree(cfg.production_root / "deploy/web_data", backup / "deploy")
    shutil.copytree(cfg.project_root / "web/public/web_data", backup / "frontend")
    pointer = load(cfg.production_root / "current.json")
    atomic_json(update.root / "publication_transaction.json",
                {"pointer": pointer, "backup": "runs/interrupted/publication_backup"})
    atomic_json(cfg.production_root / "current.json", {"dataset_version": "broken", "run_path": "runs/missing"})
    report = update.run()
    assert report["status"] == "NO_CHANGES" and snapshot(cfg) == before
    assert not (update.root / "publication_transaction.json").exists()


def test_quality_gate_never_relaxed_by_ops(base, monkeypatch):
    cfg, _, _ = base
    update, _ = updater(base, monkeypatch, [new_post(cfg)])
    parse = update.registry.excel.parse_sample
    def contaminated(item):
        result = parse(item)
        result.update(menu_quality_valid=False, unresolved_formula_values=1)
        return result
    monkeypatch.setattr(update.registry.excel, "parse_sample", contaminated)
    before = snapshot(cfg)
    report = update.run()
    assert report["status"] == "PARTIAL" and snapshot(cfg) == before
    assert "UNRESOLVED_FORMULA" in {r["reason_code"] for r in load(update.root / "review_queue.json")}


def test_changed_review_resolves_after_ready_replacement(base, monkeypatch):
    cfg, _, _ = base
    update, _ = updater(base, monkeypatch, [new_post(cfg, "1-1")], failure="UNSUPPORTED_LAYOUT")
    update.run()
    second = new_post(cfg, "1-1", content=b"fixed")
    update.collector = FixtureCollector([second])
    update.registry = registry(cfg, monkeypatch, month="01")
    report = update.run()
    assert report["status"] == "SUCCESS" and report["review"]["open_total"] == 0


def test_preserved_failed_refresh_visible_in_collector_result(tmp_path, monkeypatch):
    from collector.catalog import CatalogStore
    from collector.crawler import CorrectionsCrawler
    from test_production import settings
    cfg = settings(tmp_path)
    cfg = __import__("dataclasses").replace(cfg, raw_root=tmp_path / "raw",
        attachment_history_path=tmp_path / "history.jsonl", failures_path=tmp_path / "failures.jsonl")
    old = new_post(cfg, "1-1", content=b"x")
    CatalogStore(cfg.catalog_path).commit([old])
    crawler = CorrectionsCrawler(cfg)
    response = type("Response", (), {"content": b"html"})()
    monkeypatch.setattr(crawler.client, "get", lambda *args, **kwargs: response)
    monkeypatch.setattr(crawler.client, "post", lambda *args, **kwargs: response)
    monkeypatch.setattr(crawler.adapter, "parse_list", lambda *args: [deepcopy(old)])
    monkeypatch.setattr(crawler.adapter, "parse_detail", lambda *args: new_post(cfg, "1-1", status="failed"))
    monkeypatch.setattr(crawler.downloader, "download", lambda *args: None)
    result = crawler.collect(latest_only=True, refresh_recent=1)
    assert result.posts[0].attachments[0].status == "failed"
    assert CatalogStore(cfg.catalog_path).load()[0].attachments[0].status == "downloaded"
    assert result.posts_checked == 1 and result.status == "partial"
