from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.crawler import CorrectionsCrawler


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect corrections meal-plan source files")
    parser.add_argument("--pages", type=int, default=1, help="number of list pages (default: 1)")
    parser.add_argument("--latest-only", action="store_true", help="skip post IDs already in the catalog")
    parser.add_argument(
        "--refresh-recent",
        type=int,
        default=0,
        metavar="N",
        help="with --latest-only, recheck the N most recent meal-plan posts",
    )
    parser.add_argument("--dry-run", action="store_true", help="discover metadata without downloads or catalog writes")
    args = parser.parse_args()
    if args.pages < 1:
        parser.error("--pages must be at least 1")
    if args.refresh_recent < 0:
        parser.error("--refresh-recent must be zero or greater")
    if args.refresh_recent and not args.latest_only:
        parser.error("--refresh-recent requires --latest-only")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = CorrectionsCrawler().collect(
        pages=args.pages,
        latest_only=args.latest_only,
        refresh_recent=args.refresh_recent,
        dry_run=args.dry_run,
    )
    print(f"Collection status: {result.status.upper()}")
    print(f"Discovered meal-plan posts: {len(result.posts)}")
    print(f"Discovered attachments: {sum(len(post.attachments) for post in result.posts)}")
    print(f"Failures: {result.failure_count}")
    if result.fatal_error:
        print(f"Fatal error: {result.fatal_error}", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

