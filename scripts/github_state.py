"""GitHub fresh-checkout state: pack / restore / validate / daily."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deployment.state import pack, restore, validate, run_daily

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('pack', 'restore', 'validate', 'daily'))
    args = parser.parse_args()
    result = {'pack': pack, 'restore': restore, 'validate': validate, 'daily': run_daily}[args.command]()
    if args.command == 'validate':
        result = {'status': 'PASS', 'dataset_version': result['run_metadata']['dataset_version'],
                  'ready': result['documents']['ready'], 'meal_slots': result['records']['production_ready'],
                  'months': result['web_data']['institution_month_files']}
    print(json.dumps(result, ensure_ascii=True))
