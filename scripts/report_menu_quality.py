from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from production.quality_report import capture_baseline, compare_quality


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Capture old public artifact scan or compare the new menu-quality run")
    parser.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()
    result = capture_baseline() if args.baseline_only else compare_quality()
    if args.baseline_only:
        result = {**result, "scan": {k: v for k, v in result["scan"].items() if k != "occurrences"}}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
