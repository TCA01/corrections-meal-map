"""Copy selected source workbooks; preserve raw and worksheet/cache bytes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_deployment_fixtures import fixture_copy
from production.io import atomic_json, read_jsonl
import json

root = Path(__file__).resolve().parents[1]
production = root / 'data/production'
run = production / json.loads((production/'current.json').read_text())['run_path']
ids = {'61045-61178','59108-59036','47472-46617','56195-55886',
       '65664-66430','61519-61743','51939-51264','73262-75122','74300-76354','75768-78054','72303-74034'}
selected = [i for i in read_jsonl(run/'excel_manifest.jsonl') if i['document_id'] in ids]
assert len(selected) == len(ids)
previous_path = root/'tests/fixtures/completeness/manifest.json'
previous = {m['document_id']:m for m in json.loads(previous_path.read_text(encoding='utf-8'))} if previous_path.exists() else {}
for item in selected:
    original = root/item['local_path']
    fixture_copy(original, root/'tests/fixtures/completeness/raw'/
                 (item['document_id'] + original.suffix), item,
                 previous_sha256=previous.get(item['document_id'],{}).get('sha256'))
    item['error'] = None
atomic_json(root/'tests/fixtures/completeness/manifest.json', selected)
print(f'Prepared {len(selected)} completeness/semantic regression source workbooks')
