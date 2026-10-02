from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit.historical import HistoricalAuditor
from audit.migration import enrich_posts, migrate_current_catalog
from audit.reporting import (
    build_audit_summary,
    build_corpus_comparison,
    build_parser_priority,
    preserve_download_metadata,
    select_classification_samples,
    select_parser_samples,
    select_representative_samples,
    unknown_role_report,
    unresolved_report,
    write_json,
)
from audit.store import HistoricalAuditStore
from collector.catalog import CatalogStore
from config.settings import Settings
from institutions.master import InstitutionMaster


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit historical correctional meal-plan document metadata")
    parser.add_argument("--max-pages", type=int, default=None, help="maximum search result pages for this run")
    parser.add_argument("--no-resume", action="store_true", help="start page traversal at page 1")
    parser.add_argument("--report-only", action="store_true", help="rebuild reports without network requests")
    parser.add_argument("--sample-limit", type=int, default=24)
    parser.add_argument("--parser-sample-limit", type=int, default=40)
    parser.add_argument("--classification-sample-limit", type=int, default=24)
    args = parser.parse_args()
    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages must be at least 1")
    settings = Settings()
    master = InstitutionMaster.load(settings.institutions_path)
    current_store = CatalogStore(settings.catalog_path, settings.attachment_history_path)
    migrated, current_unresolved = migrate_current_catalog(current_store, master)
    print(f"CURRENT CATALOG MIGRATED FIELDS: {migrated}")
    if current_unresolved:
        print(f"CURRENT CATALOG UNRESOLVED: {', '.join(current_unresolved)}")

    result = None
    if not args.report_only:
        result = HistoricalAuditor(master, settings).run(
            max_pages=args.max_pages,
            resume=not args.no_resume,
        )
        print(f"HISTORICAL CRAWL STATUS: {result.status.upper()}")
        print(f"PAGES SCANNED: {result.pages_scanned}")
        print(f"NEW POSTS: {result.new_posts}")
        print(f"FAILURES: {result.failure_count}")

    historical_store = HistoricalAuditStore(settings.historical_catalog_path)
    posts = historical_store.load()
    historical_changes, _ = enrich_posts(posts, master)
    if historical_changes:
        historical_store.commit(posts)
    # Include current collected posts so reports remain useful before a full
    # historical run and duplicate post IDs remain canonical.
    combined = {post.post_id: post for post in posts}
    for post in current_store.load():
        combined[post.post_id] = post
    posts = list(combined.values())
    summary = build_audit_summary(posts, master)
    audit_root = settings.historical_catalog_path.parent
    def existing_manifest(name: str) -> list[dict[str, object]]:
        path = audit_root / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    write_json(audit_root / "audit_summary.json", summary)
    representative = preserve_download_metadata(
        select_representative_samples(posts, args.sample_limit), existing_manifest("representative_samples.json")
    )
    parser_samples = preserve_download_metadata(
        select_parser_samples(posts, args.parser_sample_limit), existing_manifest("parser_samples.json")
    )
    classification_samples = preserve_download_metadata(
        select_classification_samples(posts, args.classification_sample_limit),
        existing_manifest("classification_samples.json"),
    )
    write_json(audit_root / "representative_samples.json", representative)
    write_json(audit_root / "parser_samples.json", parser_samples)
    write_json(audit_root / "classification_samples.json", classification_samples)
    write_json(audit_root / "unresolved_institutions.json", unresolved_report(posts))
    write_json(audit_root / "unknown_document_roles.json", unknown_role_report(posts))
    baseline_path = audit_root / "phase2_20_page_baseline.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        write_json(audit_root / "corpus_comparison.json", build_corpus_comparison(baseline, summary))
    write_json(audit_root / "parser_priority.json", build_parser_priority(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if result and result.status == "fatal" else (1 if result and result.status == "partial" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
