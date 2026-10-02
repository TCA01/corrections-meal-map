from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from institutions.location_pipeline import run_location_enrichment


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="One-time static official institution marker enrichment")
    parser.add_argument("--apply", action="store_true", help="Apply validated coordinates and rebuild/sync existing bridge")
    parser.add_argument("--allow-kakao", action="store_true", help="Explicit optional fallback, using KAKAO_REST_API_KEY")
    args = parser.parse_args()
    report = run_location_enrichment(apply=args.apply, allow_kakao=args.allow_kakao)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
