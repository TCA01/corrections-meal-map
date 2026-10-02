# Meal completeness audit (3B.3)

The original Busan 2019-02-01 workbook contains 4 breakfast items, 4 lunch
items and 5 dinner items. Version 3B.2 published only the last row (kimchi).
Date numbers in weekly blocks were mistaken for independent daily meal rows.
Merged date labels also caused continuation food rows to be omitted.

Version 3B.3 distinguishes weekly anchors from daily rows, reads the full
merged-date block, preserves distinct merged food masters once, and uses the
meal-name columns rather than price, quantity or supplementary-meal columns.
Final blocks end at the actual table footer, not an arbitrary six/eight-row
cap or the bottom of a weekday-label merge. Snack weekdays below a merged
footer are excluded from layout detection. Tables explicitly described as
additions to an existing meal are preserved in REVIEW, not published as
complete meals. Original raw files and older immutable runs remain intact.
If that note is absent, a juvenile-table title together with a month of
dairy-only breakfasts triggers `SUPPLEMENTARY_SCOPE_UNCERTAIN` and REVIEW.
This is not an automatic error verdict and does not remove the source milk
or reject a single-item meal merely because its list has length one.
An explicitly staff/guard-labelled fallback table is also REVIEW, never
published as inmate meals. Its records remain available for investigation.

Each extracted record stores `source.block_bounds` and a completeness check
against food-candidate source cells and normalized token multiplicities.
Missing cells/items or extra items produce `INCOMPLETE_SOURCE_RANGE` and
REVIEW, never an invented replacement menu. Uncertain source blocks also
remain REVIEW. A legitimate single-item meal is not automatically rejected.
Identical three-meal days, mostly single-item documents and repeated single
items are investigation candidates, not automatic claims of parser errors.

## Reproducible verification

`python scripts/audit_meal_completeness.py` writes the active READY audit to
`data/production/reports/meal_completeness_audit.json`. It counts unique public
slots, scopes identical days to their institution, reopens raw workbooks and
compares structural food candidates with provenance. The audit does not mutate
the audited immutable run. `--run` and `--output` retain a baseline audit.

The 3B.2 baseline contained 415 READY documents, 37,791 public slots,
10,359 single-item slots and 9,957 incomplete source ranges. There were 121
suspicious documents. These counts are not equivalent to 121 independently
proven erroneous documents; the Busan defect is source-confirmed.

The independent full-meal golden fixture contains 24 hand-transcribed slots
from eight original workbooks: genuine XLS and XLSX, weekly column blocks,
merged-date row blocks, weekday meal-row tables, merged food cells and meals
with at least five items. Each slot records the sheet and exact source cells.
Before correction: 48/94 items recovered, precision 100%, recall 51.06%,
ordered full-meal exact match 37.50%. Precision alone hid severe omission.
Nine older single-row golden expectations were corrected from original cells;
they were not valid full-meal ground truth.
Three transcribed 2014 meals (51939-51264) remain REVIEW because the original
workbook does not confirm the historically inferred year. Their food lists
are checked but not published. The report separately gives full-parser
goldens (8 documents / 24 slots / 94 items) and the public READY subset
(7 documents / 21 slots / 82 items). The year gate was not relaxed.

The first candidate run still had footer-weekday and supplementary-scope
issues. The second candidate restored footer boundaries but left one
uncertain juvenile supplement table (75768-78054): the raw source has dairy
only at breakfast, while the same source's adjacent-month template explicitly
says it adds to existing meals. No institution-specific parser exception was
added. These undeployed candidate runs and audits were retained unchanged;
the final run is generated after the conservative scope gate above.

## Final verified dataset

`20261002T225806471013+0900-51c83fe482` (parser/policy 3B.3) reuses
all 1,204 existing raw files without downloading. READY 568, REVIEW 562,
FAILED 74; 51,771 public slots across 567 institution-month files and
32 institutions. The master remains 55/55 map-ready.

Public item counts: zero 0-item, zero 1-item, four 2-item, 12,819 3-item,
and 38,948 4+-item slots. Reopening all 568 READY raw workbooks finds no
incomplete provenance ranges, source token mismatches, identical three-meal
days or suspicion candidates under the documented rules. This is structural
evidence, not exhaustive human verification of every menu's semantics.

All 94 transcribed food items match (precision, recall and ordered exact
match 100%); the public subset separately matches all 82 items / 21 meals.
Sixteen new regressions were added. The complete local suite passes 349
tests; original files, old runs and operational archive members were verified
unchanged. Nine staff tables, two explicit supplement-only tables and one
uncertain juvenile supplement table are retained in REVIEW.

## Limits

Full-corpus structural consistency is not exhaustive human semantic review.
Golden precision/recall describe 24 meals, not a certified percentage for all
public meals. Existing slash/comma tokenization preserves alternatives as
tokens and does not decide which alternative was served. Period evidence,
source weekday/date inconsistencies and unresolved formulas remain governed
by existing validation and review policies for recognized labels. Combined
weekday/date strings are not exhaustively interpreted or calendar-certified
by this food-completeness change. Raw text and formula/cache audit
evidence are retained. No UI or new document format parser was introduced.
Some original cells also contain week-number choices such as `(1)` through
`(5)`. Their source alternatives remain visible with those labels; this
change does not select one week-specific option or certify every source
publication as an independently verified account of the meal actually served.
