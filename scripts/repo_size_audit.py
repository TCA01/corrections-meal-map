"""Audit actual Git-ignore-aware commit candidates; never stage or commit files."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deployment.audit import audit
from production.io import atomic_json

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(Path(__file__).resolve().parents[1])
    if args.output:
        atomic_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, ensure_ascii=True, indent=2))
    if args.check and result['status'] != 'PASS':
        raise SystemExit(1)
