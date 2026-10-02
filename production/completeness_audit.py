"""Read-only full-public-slot audit, source-range evidence and independent goldens."""
from collections import Counter
import json
from pathlib import Path
from parsers.excel.completeness import suspicious_meals
from parsers.excel.pipeline import ExcelMealParser
from parsers.excel.workbook_reader import read_workbook
from parsers.excel.meal_normalizer import split_menu_tokens
from parsers.excel.menu_artifacts import classify_menu_token
from .io import read_jsonl


def golden_metrics(slots, results):
    expected = predicted = correct = exact = 0
    details = []
    for slot in slots:
        records = results[slot['document_id']]['records']
        record = next((r for r in records if r['meal_date'] == slot['date']
                       and r['meal_type'] == slot['meal_type']), None)
        actual = [i['name'] for i in record['menu_items']] if record else []
        truth = slot['items']
        matches = sum((Counter(truth) & Counter(actual)).values())
        expected += len(truth)
        predicted += len(actual)
        correct += matches
        exact += truth == actual
        details.append({**slot, 'actual_items': actual, 'exact_match': truth == actual,
                        'source_cells_complete': bool(record) and set(slot['cells']) <= set(record['source']['cells'])})
    return {'documents': len({s['document_id'] for s in slots}), 'meal_slots': len(slots),
            'expected_items': expected, 'predicted_items': predicted, 'correct_items': correct,
            'menu_item_precision': correct/predicted if predicted else 0,
            'menu_item_recall': correct/expected if expected else 0,
            'full_meal_exact_match': exact/len(slots) if slots else 0, 'slots': details}


def audit_dataset(root: Path, run: Path, *, source_check=True):
    documents = {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in (run/'ready').glob('*.json')}
    distribution = Counter()
    public_records = []
    for path in (run/'web_data/menus').rglob('*.json'):
        month = json.loads(path.read_text(encoding='utf-8'))
        for day, meals in month['days'].items():
            for meal, slot in meals.items():
                distribution[len(slot['menu_items'])] += 1
                public_records.append({'meal_date': day, 'meal_type': meal,
                    'institution_id': month['institution_id'], 'menu_items': slot['menu_items']})
    # Suspicion must be scoped to institution; dates alone are not unique.
    identical = []
    for institution in sorted({r['institution_id'] for r in public_records}):
        rows = [r for r in public_records if r['institution_id']==institution]
        identical.extend({'institution_id': institution, **d}
                         for d in suspicious_meals(rows)['identical_three_meal_days'])
    manifest = {m['document_id']: m for m in read_jsonl(run/'excel_manifest.jsonl')}
    suspicious = []
    incompletes = []
    parser = ExcelMealParser(root)
    for index, (ident, result) in enumerate(documents.items(), 1):
        reasons = suspicious_meals(result['records'])['candidates']
        if source_check:
            # Re-read the actual raw workbook. Structural full-block candidates
            # are compared with old provenance, never inferred from menu length.
            if result.get('source_completeness_valid') is True:
                workbook = read_workbook(root/manifest[ident]['local_path'])
                sheet_cells = {s.name:s.cells for s in workbook.sheets}
                fresh_by_key = {}
                for r in result['records']:
                    top,bottom,left,right = r['source']['block_bounds']
                    cells = [c for c in sheet_cells[r['source']['sheet']]
                             if top <= c.row <= bottom and left <= c.column <= right
                             and not c.merged_parent and c.text]
                    food_cells = [c.coordinate for c in cells
                                  if any(classify_menu_token(t) is None for t in split_menu_tokens(c.text))]
                    expected = Counter(t for c in cells for t in split_menu_tokens(c.text)
                                       if classify_menu_token(t) is None)
                    actual = Counter(i['name'] for i in r['menu_items'])
                    if expected != actual:
                        reasons.append({'code':'SOURCE_MENU_INCONSISTENCY','meal_date':r['meal_date'],
                                        'meal_type':r['meal_type'], 'missing_items':list((expected-actual).elements()),
                                        'extra_items':list((actual-expected).elements())})
                    fresh_by_key[(r['meal_date'],r['meal_type'])] = {'source':{
                        'completeness':{'food_candidate_cells':food_cells},
                        'block_bounds':r['source']['block_bounds']}}
            else:
                fresh = parser.parse_sample(manifest[ident])
                fresh_by_key = {(r['meal_date'],r['meal_type']): r for r in fresh['records']}
            for old in result['records']:
                new = fresh_by_key.get((old['meal_date'],old['meal_type']))
                if not new:
                    reasons.append({'code':'UNVERIFIED_SOURCE_BLOCK','meal_date':old['meal_date'], 'meal_type':old['meal_type']})
                    continue
                food_cells = new['source'].get('completeness',{}).get('food_candidate_cells', [])
                missing = sorted(set(food_cells)-set(old['source']['cells']))
                if missing:
                    issue = {'code':'INCOMPLETE_SOURCE_RANGE','document_id':ident,
                             'meal_date':old['meal_date'],'meal_type':old['meal_type'],
                             'source_cells':old['source']['cells'], 'food_candidate_cells':food_cells,
                             'missing_cells':missing, 'candidate_block_bounds':new['source'].get('block_bounds')}
                    reasons.append(issue)
                    incompletes.append(issue)
        if reasons:
            suspicious.append({'document_id':ident, 'institution_id':result['institution_id'],
                               'candidate_only':True, 'reasons':reasons})
        if index % 50 == 0:
            print(f'Audited raw source {index}/{len(documents)}', flush=True)
    golden = json.loads((root/'tests/fixtures/completeness/golden.json').read_text(encoding='utf-8'))
    results = {}
    for ident in {s['document_id'] for s in golden['slots']}:
        for route in ('ready','review','failed'):
            path = run/route/f'{ident}.json'
            if path.exists():
                results[ident]=json.loads(path.read_text(encoding='utf-8'))
                break
    metrics=golden_metrics(golden['slots'],results)
    ready_slots=[s for s in golden['slots'] if s['document_id'] in documents]
    metrics['public_ready_validation']=golden_metrics(ready_slots,results)
    metrics['scope']='all transcribed parser meals; public READY subset reported separately; period gates unchanged'
    return {'dataset_version':run.name, 'ready_documents':len(documents),
            'meal_slots':sum(distribution.values()), 'item_count_distribution':dict(sorted(distribution.items())),
            'distribution':{str(n):distribution[n] for n in range(4)} | {'4+':sum(v for n,v in distribution.items() if n>=4)},
            'single_item_meals':distribution[1], 'identical_three_meal_days':identical,
            'suspicious_documents':suspicious, 'incomplete_source_ranges':incompletes,
            'source_check': 'raw_workbooks_reopened_and_structural_blocks_compared' if source_check else 'NOT CHECKED',
            'golden_validation':metrics,
            'limitations':['Structural candidates are heuristics, not proof of food semantics for every corpus cell.',
                          'Golden metrics cover hand-transcribed slots, not every READY meal.',
                          'Slash alternatives and combined dishes retain existing tokenization semantics.',
                          'Calendar consistency is not exhaustively certified for combined weekday/date source labels.']}
