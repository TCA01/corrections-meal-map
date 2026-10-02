from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from production.downloader import ProductionExcelDownloader


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--from-checkpoint", type=int)
    args = parser.parse_args()
    result = ProductionExcelDownloader().run(
        resume=args.resume, limit=args.limit, from_checkpoint=args.from_checkpoint
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
