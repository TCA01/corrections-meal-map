"""One-time selected regression workbooks, never the historical/raw archive."""
import json
import hashlib
import io
import re
from zipfile import ZipFile, ZIP_DEFLATED, is_zipfile
from xml.etree import ElementTree as ET
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from production.io import atomic_json, read_jsonl

def fixture_copy(original, target, item):
    """Strip location metadata in fixture copies, never cells/formulas/cached values."""
    payload = original.read_bytes()
    if is_zipfile(original):
        stream = io.BytesIO()
        with ZipFile(original) as source, ZipFile(stream, 'w', ZIP_DEFLATED) as output:
            for info in source.infolist():
                content = source.read(info.filename)
                # Workbook absPath, diagram creation paths, and external link targets
                # are metadata; cached values/worksheet XML remain byte-identical.
                if info.filename.endswith(('.xml', '.rels')) and not info.filename.startswith('xl/worksheets/'):
                    node = ET.fromstring(content)
                    changed = False
                    for element in node.iter():
                        for key, value in list(element.attrib.items()):
                            if re.search(r'(?<![A-Za-z])[A-Za-z]:[\\/]|file:/', value, re.I):
                                element.set(key, 'file:///external/fixture.xlsx')
                                changed = True
                    if changed:
                        content = ET.tostring(node, encoding='utf-8', xml_declaration=True)
                output.writestr(info, content)
        payload = stream.getvalue()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() not in (original.read_bytes(), payload):
        raise ValueError('refusing to replace an unrelated regression fixture')
    target.write_bytes(payload)
    item['original_source_sha256'] = item.get('sha256')
    item['sha256'] = hashlib.sha256(payload).hexdigest()
    item['file_size'] = len(payload)
    item['fixture_policy'] = 'location_metadata_redacted_cells_and_formula_caches_unchanged'
    item['local_path'] = target.relative_to(root).as_posix()

root = Path(__file__).resolve().parents[1]
cases = json.loads((root / 'tests/fixtures/menu_quality/real_cases.json').read_text(encoding='utf-8'))
source = root / 'data/production/runs' / cases['source_dataset']
manifest = read_jsonl(source / 'excel_manifest.jsonl')
ids = {c['document_id'] for c in cases['cases']}
selected = [i for i in manifest if i['document_id'] in ids]
if len(selected) != len(ids):
    raise ValueError('missing regression sources')
for item in selected:
    original = root / item['local_path']
    target = root / 'tests/fixtures/menu_quality/raw' / original.name
    fixture_copy(original, target, item)
atomic_json(root / 'tests/fixtures/menu_quality/manifest.json', selected)
samples = json.loads((root / 'data/audit/parser_samples.json').read_text(encoding='utf-8'))
excel = [i for i in samples if i['extension'] in ('xlsx', 'xls')]
for item in excel:
    original = root / item['local_path']
    target = root / 'tests/fixtures/excel_samples/raw' / (f"{item['post_id']}-{item['attachment_id']}" + original.suffix)
    fixture_copy(original, target, item)
    item['duplicate_of'] = None
atomic_json(root / 'tests/fixtures/excel_samples/manifest.json', excel)
print(f'Selected {len(excel)} Excel parser fixtures')
print(f'Selected {len(selected)} small public Excel regression fixtures')
