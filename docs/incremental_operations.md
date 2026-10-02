# Phase 4A: local exception-only operations

`python scripts/daily_update.py` is the local orchestrator. It does not install a
scheduler, crawl historical pages, deploy externally, or change React sources.
Use the project virtual environment. `--refresh-recent N` overrides
`Settings.ops_refresh_recent` (default 10 existing recent meal posts);
`Settings.refresh_max_pages` (20) bounds traversal. New posts are handled separately
from the recent-existing counter. Requests retain the collector's delay/retries.

`--dry-run` downloads and checks recent files into an isolated operational catalog
and raw store, writes diagnostics/review/report/health, and validates proposed
staging. It NEVER changes current, deploy, frontend data, or processed state.
An eligible dry run can report SUCCESS with `published=false`; it is not a
publication. Retained staging and raw files are evidence, not active datasets.

## Data and outcomes

- `data/ops/catalog/posts.jsonl`: separate collector state, initially seeded from
  existing audit/catalog and active production hashes. Original catalog/raw remain intact.
- `data/ops/raw`: new raw downloads; old raw files are never deleted.
- `data/ops/runs/<id>/candidates.json`: observed attachment metadata/change classification.
- `data/ops/runs/<id>/documents`: private parser results and new-layout diagnostics.
- `data/ops/processed_sources.json`: terminal outcomes keyed by source and SHA;
  unchanged attachments (including quarantined ones) are not reparsed.
- `data/ops/review_queue.json`: stable source+reason identity, OPEN/RESOLVED/IGNORED.
  Successful replacement resolves open issues. Ignored records remain ignored.
- `data/ops/parser_drift.json`: unique document+SHA observations (including base READY
  families); each report includes family totals. Counts are observations, not public slots.
- `data/ops/latest_report.json`, per-run report, `health.json`: operational status,
  publication/counts, timestamps, open exceptions and seven-day stale readiness.

Role classification and canonical institution resolution reuse the existing
rules/master. Inmate/mixed XLSX/XLS use the registry's existing Excel parser and
unchanged strict production gate. Actual signatures distinguish PDF/HWP/HWPX
from Excel; these are UNSUPPORTED_FOR_PRODUCTION, not corrupt spreadsheets.
Unknown layout returns REVIEW/NEW_LAYOUT with structural diagnostics, not a forced
closest-layout parse. Unknown/malformed bytes fail validation. Known other-role
attachments are OUT_OF_SCOPE; ambiguous roles/institutions enter review.
Unsupported format is recorded independently of those metadata problems: a PDF
with an unresolved institution can enter REVIEW for that reason, while its
`production_support` remains UNSUPPORTED_FOR_PRODUCTION. Processing counters are
mutually exclusive outcomes, not a count of every reason on a document.

Review reason codes: NEW_LAYOUT, UNSUPPORTED_FORMAT, UNRESOLVED_INSTITUTION,
AMBIGUOUS_DOCUMENT_ROLE, MISSING_DATE, MISSING_MEAL, UNRESOLVED_FORMULA, EXCEL_ERROR,
MENU_ARTIFACT, DATA_CONFLICT, DOWNLOAD_FAILED, SOURCE_CHANGED, VALIDATION_FAILED,
SOURCE_CHANGED_REVIEW_REQUIRED. A failed refresh retains its old collector canonical
attachment but remains observable in run outcomes and failure logs.

## Publication safety

Validate current routed documents/index/menus and existing served contract first.
Read the immutable base JSON; never reparse its 1,204 raw files. READY additions
replace only their identical source ID, then conflict-check against other READY
sources and against one another. Rejected replacements restore the base source
before repeating conflict checks. Different-content conflicts quarantine NEW sources
only; identical menus preserve all provenance IDs. Invalid replacements retain old
READY and create SOURCE_CHANGED_REVIEW_REQUIRED. Missing sources are never deleted.

Copy the immutable base, regenerate ONLY affected institution/year/month files,
rebuild availability/report counts, prove untouched files byte-identical, and validate
dataset consistency, provenance/master/URLs, public contract, and menu lint.
Prepare both export and frontend copies before touching publication.

`current.json` is an atomic file replacement; immutable run directory promotion is
a rename. Web bundle promotion uses existing whole-directory staged rename with
rollback. **Non-empty directory swaps are two renames, not a single atomic operation;
there can be a brief missing-path interval.** No multi-file transaction is globally
atomic. A durable publication journal and retained old copies restore pointer and
both bundles on exceptions or on the next locked run after a crash. A stopped
process cannot perform recovery until an operator or later run resumes it.
Concurrent non-daily publication commands must not run during daily operations.
Daily checks the base pointer again before commit and refuses stale-base publication.

Exit codes: SUCCESS=0, NO_CHANGES=0, PARTIAL=1 (isolated exceptions; may publish good
documents), FATAL=2 (site initial access/current/staging/publication failure), LOCKED=3.
Locked callers do not overwrite the running owner's shared report. All normal run
reports record their actual status; health contains no local paths or tracebacks.
Successful publication or a clean no-change run updates last_successful_update;
an entirely partial failing run does not reset that clock. Dry runs do not reset it.

## Lock and operator work

O_EXCL lock ownership is token-checked. Locks older than six hours can be reclaimed
only on the same host AND with a demonstrably dead PID. Retain stale lock evidence.
Live, foreign, malformed, or uncertain locks are never automatically stolen. A
recovery guard arbitrates concurrent stale reclaimers; interrupted guards need
operator inspection. Verify no owner is running before manually repairing locks.

Operators inspect OPEN review items and private per-run diagnostics, correct source
metadata or extend the parser/registry with tests, then explicitly request reevaluation
of the affected processed-source entry (not a daily historical reparse). Automatic
parser-policy upgrades/review replays are not part of Phase 4A. Downloads without SHA
are retried on later refreshes; quarantined identical SHA is intentionally cached.
Do not automatically delete sources because they disappeared from recent pages.

No scheduler/hosting is configured. A scheduler must understand PARTIAL vs FATAL,
safe lock recovery, network access and retention of accumulating raw/staging/backups.
Health is private local output only; public UI health integration is a later phase.
