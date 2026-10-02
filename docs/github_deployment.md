# Phase 5A: lean repository and GitHub Pages

## Persistent data classification

| Class | Data | Policy |
| --- | --- | --- |
| A: version-controlled | Python/React sources, tests, configs, parser rules, official institution master, location review manifest | Keep in repository |
| A: version-controlled | `web/public/web_data/` | Current READY public build input only; about 36 MB |
| A: version-controlled | `data/github/state.zip`, `state.json`, `review_queue.json`, `health.json` | One compressed current operational baseline, not all previous immutable runs |
| A: test fixtures | 19 selected Excel parser samples and 4 menu-quality workbooks | Small, official public regression fixtures; not the raw corpus |
| B: regenerable | `node_modules`, `dist`, Python environment/cache, staging, transient reports, downloads | Ignore; regenerate on runner |
| C: useful local archive | 1,204 production originals, historical raw archive, previous production runs, rollback backups, location HTML cache/audit | Preserve locally; never commit wholesale |

The current engine reads routed READY/REVIEW/FAILED results and their manifest, not merely public months. Omitting them breaks incremental validation/merge. `state.zip` contains just this current baseline, its small production report/metadata, and operational catalog, processed-source SHA state, parser drift, review queue, health, and attachment change history when present. It contains no raw files, parsed duplicates, old runs, local locks, staging, transaction journals, or previous bundles. Monthly menus are stored once as public JSON and reused during restore.

The archive is deterministic, hash-checked, allowlisted, bounded to 300 MB inflated, and only restored into a fresh checkout. Machine-specific diagnostic strings are redacted in the *copy*, not in existing local production. Internal repository state is readable if the repository is public, but it is not included in the Pages artifact. Relative source paths and official URLs are provenance, not credentials. The audit opens the archive rather than treating its compressed bytes as already safe.

## Local setup

```sh
python -m venv .venv
# Activate .venv using the command for your shell.
python -m pip install -r requirements.txt
# Only a new checkout without data/production/current.json:
python scripts/github_state.py restore
python -m pytest
python scripts/github_state.py validate
python scripts/repo_size_audit.py --check
cd web
npm ci
npm run test
npm run build
cd ..
node scripts/verify_web_build.mjs
```

The local historical-integrity test passes with the full local archive. In a lean checkout it explicitly skips that *one archival-only* check; all parser, collector, operations, publication and deployment regression tests still run. Fixtures no longer require the historical archive. Dependencies are fully declared in requirements/package-lock; Python 3.11 and Node 24 are used by Actions. The selected workbook copies have machine-location XML attributes removed; cells, formulas and formula caches remain unchanged. Fixture manifests distinguish source SHA from sanitized fixture SHA. Original raw files are never edited.

`python scripts/github_state.py pack` prepares a new portable baseline from an already validated local current production. Do not pack an interrupted transaction. It does not change current production. `python scripts/verify_clean_checkout.py` copies only Git-ignore-aware commit candidates into a new ignored `tmp/` directory for independent testing.

## Frontend base path

Local/custom-domain root: default `/`. Project Pages: configure-pages supplies its base path and the workflow passes it as `VITE_BASE_PATH`. Local subpath check (PowerShell): `$env:VITE_BASE_PATH='/repository-name/'; npm run build`; remove the environment variable afterwards. Default data fetch is `import.meta.env.BASE_URL + 'web_data'`; an explicit `VITE_DATA_BASE_URL` remains supported. There is no runtime geocoder or new public health endpoint.

## First GitHub setup — user action required

No local Git repository or GitHub remote existed at implementation time. This phase does not create a remote, authenticate, push, or deploy externally.

1. Create a GitHub repository under your account, with default branch `main`. Public repository is the simplest Pages/free Actions setup; check your plan if private.
2. Initialize the local repository with `git init -b main`; add your chosen remote. Run the repository audit before staging.
3. Stage sources/configs/tests/docs/workflows, `requirements.txt`, `.gitignore`, `README.md`, `web/`, `data/github/`, and the two allowed institution JSON files. **Do not force-add ignored data**. Inspect `git diff --cached --stat` and staged file names; then commit and push `main` yourself.
4. Settings → Pages → Build and deployment → Source: **GitHub Actions**. Permit the Actions bot to write repository contents. If branch protection forbids bot pushes, grant a narrowly scoped allowed mechanism or use a human-reviewed PR policy; this workflow intentionally does not bypass protection or force-push.
5. Allow the `github-pages` environment to deploy from `main`. Run **Deploy Pages** manually, then **Daily meal update** manually. Verify logs, summary, repository data commit, and the live site URL.

No extra PAT, geocoder secret, notification service or developer PC is needed for the prepared standard flow. GitHub's own default token is supplied by Actions.

## Daily schedule, commit and deployment policy

- Cron: `37 23 * * *` — **23:37 UTC / next-day 08:37 KST**, once daily. This is a morning check, not a claim that the source guarantees an update before that time. Manual `workflow_dispatch` is also enabled.
- The actual engine exit codes are SUCCESS=0, NO_CHANGES=0, PARTIAL=1, FATAL=2, LOCKED=3. Only 0/1 with a matching fresh report may continue. PARTIAL must pass the same current dataset and web validators as SUCCESS.
- NO_CHANGES never commits. Timestamp-only repeated PARTIAL also does not commit. New review/processed state may make a small review-only commit without rebuilding/deploying the website. Out-of-scope-only NO_CHANGES state is not persisted.
- A READY publication commits exactly the public bundle and four portable-state files. Raw downloads, logs, caches, staging and backups are never staged. Full backend tests and current dataset/menu/web checks run before commit; changed READY data also runs frontend tests/build and built-bundle checks.
- The bot uses `github-actions[bot]`, an explicit `git add --` allowlist, and ordinary non-force push. A concurrent human push causes rejection; do not silently rebase generated data.
- Daily/manual updates share `corrections-daily-update` concurrency with no cancellation. The existing local exclusive lock remains active. Pages deployments have their own serialized concurrency group.
- Human source/public-data pushes to `main` trigger Deploy Pages. Daily bot pushes use the built-in GITHUB_TOKEN, which does **not** trigger a new push workflow. Therefore the daily workflow explicitly calls the reusable Pages workflow with the successfully committed SHA. No extra secret is needed. [GitHub token event rules](https://docs.github.com/en/actions/concepts/security/github_token).
- The Pages artifact is only `web/dist`; failed acquisition, validation, tests, push, or deployment leaves the last successfully deployed site intact. No internal health, archive or raw data is copied into `dist`.

## Operational limits

Scheduled runs are not a precise timer: GitHub may delay or drop jobs under load. A public repository with no activity for 60 days can have scheduled workflows disabled. With a no-change/no-empty-commit policy this means genuinely zero-maintenance indefinite scheduling cannot be guaranteed. Check Actions periodically and manually re-enable scheduling if disabled; the last static Pages site remains available. [GitHub schedule limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The compressed current baseline is approximately 5 MB initially; Git history still grows on real publications. Run the size audit periodically; archive old history externally if needed rather than force-pushing casually. Automated raw files are runner-local and expire with the job. Re-fetch a quarantine source from its official URL, verify SHA, and retain important corrected-source evidence externally if required. Full long-term raw archival is deliberately not provided by this repository.

Existing Vitest 3.x dev dependencies currently report two moderate audit findings related to its development mock server. CI uses `vitest run`, and Pages contains only built static output, not that server. Do not expose the test/dev server publicly. A tested major-version upgrade is separate maintenance; no automatic breaking `npm audit fix --force` was applied.

Data scope remains official public **inmate meal plans**, with only Excel READY results published. PDF/HWP/HWPX, unknown layouts and uncertain records stay quarantined. No new parser, OCR/VLM, institution/coordinate change, external notification integration, or UI redesign is introduced.
