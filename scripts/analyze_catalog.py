from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.catalog import CatalogStore
from config.settings import Settings


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Summarize the local collection catalog")
    parser.add_argument("--catalog", type=Path, default=Settings().catalog_path)
    args = parser.parse_args()
    posts = CatalogStore(args.catalog).load()
    attachments = [item for post in posts for item in post.attachments]
    institutions = Counter(post.institution_name for post in posts)
    file_types = Counter(item.extension for item in attachments)
    years = Counter(str(post.meal_year or (post.published_date or "unknown")[:4]) for post in posts)
    months = Counter(f"{post.meal_year or 'unknown'}-{post.meal_month:02d}" if post.meal_month else "unknown" for post in posts)
    print(f"TOTAL POSTS\n{len(posts)}\n")
    print(f"TOTAL ATTACHMENTS\n{len(attachments)}\n")
    _section("INSTITUTIONS", institutions)
    _section("FILE TYPES", Counter({kind: file_types[kind] for kind in ("xlsx", "xls", "pdf", "hwp", "hwpx", "csv", "unknown")}))
    _section("YEAR DISTRIBUTION", years)
    _section("MONTH DISTRIBUTION", months)
    return 0


def _section(title: str, values: Counter[str]) -> None:
    print(title)
    for key, count in sorted(values.items()):
        print(f"- {key}: {count}")
    print()


if __name__ == "__main__":
    raise SystemExit(main())

