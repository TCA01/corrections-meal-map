"""Source-backed coverage checks; suspicion alone never rejects a one-item meal."""
from collections import Counter, defaultdict
from .meal_normalizer import split_menu_tokens
from .menu_artifacts import classify_menu_token


def source_coverage(records, sheet):
    issues = []
    for record in records:
        bounds = record.source.get('block_bounds')
        if not bounds:
            issues.append({'code': 'UNVERIFIED_SOURCE_BLOCK', 'severity': 'warning'})
            continue
        top, bottom, left, right = bounds
        food_cells = [c for c in sheet.cells if top <= c.row <= bottom
                      and left <= c.column <= right and not c.merged_parent
                      and c.text and any(classify_menu_token(t) is None
                                         for t in split_menu_tokens(c.text))]
        expected = Counter(t for c in food_cells for t in split_menu_tokens(c.text)
                           if classify_menu_token(t) is None)
        actual = Counter(item.name for item in record.menu_items)
        missing_cells = sorted({c.coordinate for c in food_cells} - set(record.source['cells']))
        missing_items = list((expected - actual).elements())
        extra_items = list((actual - expected).elements())
        record.source['completeness'] = {'food_candidate_cells': [c.coordinate for c in food_cells],
                                         'expected_items': sum(expected.values()),
                                         'extracted_items': sum(actual.values()),
                                         'missing_cells': missing_cells, 'missing_items': missing_items,
                                         'extra_items': extra_items}
        if missing_cells or missing_items or extra_items:
            issues.append({'code': 'INCOMPLETE_SOURCE_RANGE', 'severity': 'warning',
                           'meal_date': record.meal_date, 'meal_type': record.meal_type,
                           'missing_cells': missing_cells, 'missing_items': missing_items,
                           'extra_items': extra_items})
    return {'source_completeness_valid': not issues, 'issues': issues}


def suspicious_meals(records):
    """Return review candidates, NOT assertions that the source is wrong."""
    by_day = defaultdict(dict)
    singles = Counter()
    reasons = []
    for r in records:
        items = tuple(i['name'] for i in r['menu_items'])
        by_day[r['meal_date']][r['meal_type']] = items
        if len(items) == 1:
            singles[items] += 1
            if len(r.get('source', {}).get('cells', [])) > 1:
                reasons.append({'code': 'MULTIPLE_CELLS_SINGLE_ITEM', 'meal_date': r['meal_date'],
                                'meal_type': r['meal_type']})
    identical = []
    for day, meals in by_day.items():
        if len(meals) == 3 and len(set(meals.values())) == 1:
            items = next(iter(meals.values()))
            identical.append({'meal_date': day, 'menu_items': list(items),
                              'code': 'IDENTICAL_SINGLE_ITEM_THREE_MEALS' if len(items)==1
                              else 'IDENTICAL_THREE_MEALS'})
    reasons.extend(identical)
    if records and sum(singles.values()) / len(records) >= .9:
        reasons.append({'code': 'MOSTLY_SINGLE_ITEM', 'single_slots': sum(singles.values())})
    for items, count in singles.items():
        if count >= 15:
            reasons.append({'code': 'LONG_SINGLE_ITEM_REPETITION', 'menu_items': list(items), 'slots': count})
    return {'identical_three_meal_days': identical, 'candidates': reasons}
