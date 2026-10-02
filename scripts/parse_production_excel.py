from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from production.pipeline import ProductionExcelPipeline


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--from-checkpoint", type=int)
    parser.add_argument("--new-run", action="store_true")
    args = parser.parse_args()
    report = ProductionExcelPipeline().run(
        resume=args.resume, limit=args.limit, from_checkpoint=args.from_checkpoint, new_run=args.new_run
    )
    summary = {key: value for key, value in report.items()
               if key not in {"conflicts", "new_layout_candidates", "download_failures", "download_failure_details"}}
    summary["conflict_slots"] = len(report.get("conflicts", []))
    summary["new_layout_candidates_count"] = len(report.get("new_layout_candidates", []))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
