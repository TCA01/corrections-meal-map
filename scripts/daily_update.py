"""Phase 4A local incremental operations. No scheduler/deployment is configured."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from operations.daily import DailyUpdater
from operations.state import RunLocked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-recent", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Collect/validate in isolation; do not publish or advance processed state")
    args = parser.parse_args()
    try:
        report = DailyUpdater().run(refresh_recent=args.refresh_recent, dry_run=args.dry_run)
    except RunLocked:
        print("DAILY UPDATE LOCKED — another update or an uncertain lock exists")
        return 3
    print(f"DAILY UPDATE COMPLETE: {report['status']}" + (" (DRY RUN; not published)" if args.dry_run else ""))
    print(f"Checked posts: {report['site']['posts_checked']} / New attachments: {report['attachments']['new']}")
    for label, key in [("AUTO READY", "auto_ready"), ("REVIEW", "review"), ("FAILED", "failed"), ("UNSUPPORTED", "unsupported")]:
        print(f"{label}: {report['processing'][key]}")
    print(f"NEW LAYOUT: {report['review']['new_layout_count']}")
    print(f"Published: {report['publication']['published']} / Current dataset: {report['publication']['dataset_version']}")
    for institution, year, month in report["publication"]["touched_months"]:
        print(f"- {institution} / {year}-{month:02d}")
    if report.get("fatal_reason"):
        print(f"Fatal reason: {report['fatal_reason']} ({report.get('error_type', 'site access')})")
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
