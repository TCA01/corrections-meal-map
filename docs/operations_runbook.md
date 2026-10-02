# Operations runbook

## 몇 달 뒤 다시 확인할 때

사이트는 정적 파일입니다. **Daily meal update**가 수집·검증하고 **Deploy Pages**가 공개합니다. 갱신 실패 시 마지막 정상 사이트를 유지합니다.

| 상황 | 먼저 할 일 |
| --- | --- |
| 사이트가 갱신되지 않음 | Actions의 최근 실행과 summary 확인. NO_CHANGES는 정상입니다. 예약이 꺼졌다면 다시 활성화하고 수동 실행하세요. |
| Action 실패 | 처음 실패한 단계부터 확인. 네트워크 실패는 재실행하고, push 충돌은 최신 main에서 재실행합니다. force-push나 검증 완화는 하지 않습니다. |
| NEW_LAYOUT 발생 | `data/github/review_queue.json`의 공식 원본 URL과 식별자를 확인하고 개발자에게 표본·규칙·테스트 추가를 요청합니다. |
| review/health 확인 | 위 파일과 `data/github/health.json`은 운영 기록입니다. Pages에는 공개하지 않습니다. 실패 실행은 commit되지 않으므로 Actions 기록도 확인하세요. |
| parser 수정 후 재평가 | 현재 한 번에 재처리하는 CLI는 없습니다. 동일 SHA는 자동 재처리되지 않습니다. 기존 정상 데이터와 병합하는 명시적 재평가가 필요합니다. |
| 마지막 정상 데이터로 복구 | 공개 데이터와 압축 운영 상태를 **함께** 되돌리고 검증한 뒤 배포합니다. 월별 JSON만 따로 되돌리지 않습니다. |
| 교정본부 HTML 변경 | `collector/site_adapter.py`와 HTML fixture부터 확인합니다. 수집 실패가 기존 정상 attachment를 덮어쓰면 안 됩니다. |

공개 repository에 60일간 활동이 없으면 GitHub 예약 실행이 비활성화될 수 있습니다. 빈 commit으로 우회하지 않고 주기적으로 Actions 상태를 확인합니다. 아래에는 각 상황의 상세 절차가 있습니다.

Read this after months away: the site is static. Source acquisition and parsing happen in **Daily meal update**; publishing happens in **Deploy Pages**. A failed update must never replace the last normal site. See [deployment setup and state classification](github_deployment.md).

## A. The site is not updating

1. Open GitHub → Actions → Daily meal update. Check the last run date and summary: status, checked posts, AUTO READY, REVIEW, NEW LAYOUT, dataset updated.
2. NO_CHANGES with a recent successful run is normal. A new unsupported layout can also leave the public version unchanged.
3. If there are no recent runs, check default branch `main`, Actions enabled, cron, and whether the 60-day inactivity rule disabled scheduling. Re-enable it and run workflow_dispatch manually. Cron may be delayed; it is not an SLA.
4. If a data commit exists but the site is old, inspect the reusable deploy job and the github-pages environment. Verify Settings → Pages uses Actions. Check the live manifest dataset_version against repository `web/public/web_data/manifest.json`.

## B. GitHub Action failed

Find the first failing step, not only the final summary. FATAL=2 means acquisition/validation/publication failure; LOCKED=3 means an owner or uncertain lock exists. PARTIAL=1 is allowed only after validators succeed. Missing/mismatched reports fail closed.

Network/source outages: wait and rerun manually; do not lower validation gates. Dependency/build failures: reproduce with declared requirements and `npm ci`, not a copied local environment. A rejected non-fast-forward push means a human changed main during the run; rerun from the latest main, never force-push generated state. Branch-protection errors require repository-owner permission changes, not a secret embedded in YAML. Pages errors require Pages/environment permissions. No successful deploy means the last successful site stays unchanged.

Never manually delete an uncertain live local lock. Inspect its owner first. Disposable GitHub runners have isolated workspaces, and concurrency serializes daily/manual workflow runs.

## C. NEW_LAYOUT

Inspect `data/github/review_queue.json`: reason_code, official source_url, post/attachment IDs, filename and institution. No public meal is inferred from an unknown layout. Download the source from its official URL into an ignored local directory and verify its SHA against the restored catalog/processed-source manifest. The daily runner does not retain raw files long-term.

Ask a maintainer to add a representative fixture, parser/layout rule, and regression test. Do not change `production_eligible` or gate outcomes by hand. XLSX/XLS extensions can differ from actual signatures; use existing format detection. Unsupported PDF/HWP/HWPX stays unsupported until a separately authorized parser phase.

## D. Review queue and health

Repository review/health copies are internal operational artifacts, **not Pages web_data**. OPEN requires inspection; RESOLVED and IGNORED history is preserved. Repeated last_seen updates alone do not make commits. New review-only results persist small state without a website deploy. Full source/result metadata is available after a fresh `github_state.py restore`; no source raw archive is included.

FATAL/LOCKED runs make no repository state commit. Inspect their Actions logs/summary. A stale health copy on main is not proof that a later failed run never occurred. The public frontend continues using manifest last_updated only.

## E. After parser fixes: re-evaluate quarantine

Start with a fresh clone, install requirements, restore portable state, fetch the exact quarantined original, and check its SHA. Run full tests including the new representative regression before publishing.

**The current daily CLI has no automatic reprocess/retry-quarantine option.** An unchanged SHA is deliberately not reparsed just because code changed. Removing one processed-state entry is not sufficient when the base manifest also knows that SHA. Do not delete the whole catalog or re-run a subset production build into current: that can discard existing READY data.

A maintainer must perform an explicit reviewed replay through existing `ParserRegistry.process`, `merge_ready`, and `IncrementalPublisher.prepare/publish`, preserving the active base and running the existing validation gates. Archive the corrected source evidence locally. Then run `github_state.py validate`, pack the corrected portable baseline, review the public/state diff, and commit those allowlisted files together. This manual replay is a current operational limitation, not a promised existing one-command feature.

## F. Roll back to the last normal production

For GitHub, use a reviewed **git revert of the complete generated data commit** (public web_data and data/github files together), not individual monthly JSON edits. Reverting only public files breaks the archive/public hash contract. On a fresh checkout, restore and validate the reverted state, run backend/frontend tests/build, then push the reviewed revert. Deploy Pages will publish it. Repository owner controls branch protection/approval.

For local interrupted operations, retain `publication_transaction.json` and its backup: the existing next-run recovery restores the old pointer/bundles. Do not delete backups or point current at staging. For a deliberate older local rollback, select an intact previously validated run and rebuild/sync through the existing bridge only after verifying the master and full dataset. Preserve the current tree before changing its pointer.

## G. Corrections site HTML changed

Check official HTML fixtures and collector list/detail parsing first. Keep site-specific changes inside `collector/site_adapter.py`; downloader, catalog preservation, parser gates and publication logic should remain unchanged. Add captured sanitized fixtures and multi-page regression tests. The collection safety limit must stay bounded. A failed attachment refresh must keep the previous canonical attachment; a failed initial list must stop publication. Test partial failures and failed refresh preservation before manual workflow execution.

## Final checklist

```sh
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

No Slack/email notification is configured. Use Actions summaries and GitHub's workflow failure UI. Check schedule health periodically; do not use empty daily commits to conceal inactivity restrictions.
