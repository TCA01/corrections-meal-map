from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from production.web_bridge import WebDataBridge

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", action="store_true")
    args = parser.parse_args()
    bridge = WebDataBridge()
    path = bridge.settings.project_root / "web/public/web_data" if args.frontend else bridge.deploy_path
    print(json.dumps(bridge.validate(path), ensure_ascii=False, indent=2))
