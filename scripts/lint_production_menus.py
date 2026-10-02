from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from production.io import atomic_json
from production.menu_lint import scan_public_menus
from production.web_bridge import WebDataBridge


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Reject definite non-menu artifacts in public READY menu_items")
    parser.add_argument("--web-data", type=Path, help="default: active immutable run web_data")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.web_data or WebDataBridge().active_run()[1] / "web_data"
    result = scan_public_menus(root)
    if args.output:
        atomic_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != "occurrences"}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
