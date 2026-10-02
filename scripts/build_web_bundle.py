from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from production.web_bridge import WebDataBridge


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build deploy web_data from the active immutable run")
    parser.add_argument("--fixtures", action="store_true", help="also build two real cross-contract month fixtures")
    args = parser.parse_args()
    bridge = WebDataBridge()
    result = bridge.build()
    if args.fixtures:
        result["cross_contract_fixtures"] = bridge.build_fixtures()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
