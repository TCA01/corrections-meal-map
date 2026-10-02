# Corrections Meal Data Map — collection and document-audit foundation

대한민국 교정기관이 공개한 **수용자 식단표** 게시물의 메타데이터와 원본 첨부파일을 보존하는 수집기입니다. 2단계에서는 공식 기관 기준정보와 과거 게시물 메타데이터 audit, 대표 원본의 구조 조사까지 제공합니다. 문서 본문을 정형 데이터로 변환하는 parser, OCR, AI API, 데이터베이스, 웹 UI는 아직 포함하지 않습니다.

## 설계 원칙

- `collector/site_adapter.py`에 교정본부 HTML 선택자와 URL 규칙을 격리했습니다.
- 요청은 기본 동시성 1, 1.5초 간격, timeout, retry와 exponential backoff를 사용합니다.
- 목록·상세·첨부 실패는 `data/failures/failures.jsonl`에 따로 기록하며 다음 항목을 계속 처리합니다.
- 원본은 `data/raw/{기관}/{연도}/{월}/`에, 가공 메타데이터는 `data/catalog/posts.jsonl`에 분리합니다.
- SHA-256이 같은 파일은 두 번째 원본을 저장하지 않고 `duplicate_of`를 기록합니다.
- 같은 게시물의 같은 첨부를 재확인한 경우 최초 `downloaded` canonical 메타데이터를 보존합니다.
- refresh 다운로드가 실패하면 기존 정상 첨부를 유지하고 실패 사실만 `data/failures/failures.jsonl`에 남깁니다.
- 동일 attachment ID의 SHA-256이 바뀌면 최신 버전은 메인 카탈로그에 두고 이전/신규 버전 관계를 `data/catalog/attachment_history.jsonl`에 중복 없이 추가합니다. 이전 원본은 삭제하지 않습니다.
- `local_path`와 `duplicate_of`는 운영체제 독립적인 프로젝트 상대 storage key로 기록합니다. 카탈로그에만 있고 현재 환경에 실제 원본이 없으면 새 다운로드를 폐기하지 않습니다.
- 신규 카탈로그는 임시 파일 전체를 검증한 뒤 원자적으로 교체합니다. 검증 실패 시 기존 정상 카탈로그는 유지됩니다.
- 유료 API나 상시 서버가 필요 없는 파일 기반 구조입니다.

## 설치 및 실행

Python 3.11 이상을 권장합니다.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/collect.py --pages 1
```

선택 옵션:

```powershell
python scripts/collect.py --latest-only
python scripts/collect.py --latest-only --refresh-recent 10
python scripts/collect.py --pages 3 --dry-run
```

`--dry-run`은 목록과 상세 메타데이터만 탐색하며 다운로드와 카탈로그 쓰기를 하지 않습니다.
`--refresh-recent N`은 `--latest-only`와 함께 사용하여 최신 기존 식단 게시물 N건을 찾을 때까지 필요한 목록 페이지를 자동 탐색합니다. 신규 게시물은 항상 처리하며 N건 계산에서는 제외됩니다. 무한 탐색을 막기 위한 기본 안전 한계는 20페이지입니다. 야간 수집에서는 이 모드를 사용하면 전체 과거 게시물을 매번 받지 않으면서 원 게시물의 첨부 교체를 감지할 수 있습니다.

CLI 종료코드는 정상 수집(신규 0건 포함) `0`, 일부 상세·첨부 실패 `1`, 최초 목록 페이지를 가져오지 못한 치명적 실패 `2`입니다.

## 통계와 테스트

```powershell
python scripts/analyze_catalog.py
python -m pytest
```

통계는 게시글·첨부 수, 기관별 게시글 수, 확장자, 연도 및 월 분포를 출력합니다. 지원 확장자는 `xlsx`, `xls`, `csv`, `pdf`, `hwp`, `hwpx`이며 나머지는 삭제하지 않고 `unknown`으로 분류합니다.

## 기관 기준정보

`data/institutions/institutions.json`은 교정본부의 전국 교정기관 안내를 근거로 만든 55개 현행 기관 master입니다. 원문 기관명은 카탈로그의 `institution_name`에 그대로 보존하고, 정확히 확인된 기관만 안정적인 `institution_id`를 추가합니다. 축약명과 게시판 표기 변형은 명시적인 alias로만 매핑하며 fuzzy matching으로 추측하지 않습니다.

공식 페이지를 다시 조회해 master를 갱신하려면 다음 명령을 사용합니다.

```powershell
python scripts/build_institutions.py
```

## 과거 문서 메타데이터 audit

다음 명령은 공식 게시판에서 제목 검색어 `식단`의 결과를 순차 탐색합니다. 이 과정은 첨부 원본을 내려받지 않고 게시물·첨부 메타데이터만 수집합니다. 요청은 동시성 1과 기존 수집기의 안전한 지연·재시도 정책을 공유합니다.

```powershell
python scripts/audit_documents.py
python scripts/audit_documents.py --max-pages 20
python scripts/audit_documents.py --report-only
```

- 진행 상태는 `data/audit/checkpoint.json`에 페이지 단위로 저장되어 중단 후 재개됩니다.
- 게시물은 `data/audit/historical_posts.jsonl`에 원자적으로 저장하며 `post_id` 중복을 방지합니다.
- 개별 페이지나 상세 조회 실패는 `data/audit/failures.jsonl`에 기록하고 가능한 작업을 계속합니다.
- 기본 최대 탐색 범위는 400페이지이며 게시판 끝을 감지하면 먼저 종료합니다.
- 마지막 페이지에 도달한 실행은 checkpoint의 `completed`를 `true`로 기록하며 이후 재실행은 네트워크를 다시 순회하지 않습니다.
- `--no-resume`은 1페이지부터 다시 확인하되 기존 저장 데이터는 중복 생성하지 않습니다.

audit 결과는 확장자·연도·월·기관·문서 역할 분포와 기관×형식, 형식×연도 교차표를 `data/audit/audit_summary.json`에 저장합니다. `parser_priority.json`은 `inmate+mixed` 문서만으로 형식별 parser 우선순위를 계산하고, `corpus_comparison.json`은 20페이지 중간 결과와 완성 corpus의 형식 비율을 비교합니다. 미해결 기관과 보수적으로 `unknown` 처리한 문서 역할은 각각 별도 JSON 보고서에 남깁니다. 문서 역할은 파일명, 게시물 제목, sibling 첨부명을 deterministic rule로 함께 보되 확정 근거가 약하면 `unknown`을 유지합니다.

대표 표본은 목적별로 분리됩니다.

- `data/audit/parser_samples.json`: `inmate`와 `mixed`만 포함하는 parser 개발용 표본
- `data/audit/classification_samples.json`: staff, supplementary, other, unknown 및 복합 게시물 검증용 표본
- `data/audit/representative_samples.json`: 전체 corpus 개요용 호환 manifest

parser 표본만 다운로드하려면 다음 명령을 사용합니다. 전체 historical 첨부는 다운로드하지 않습니다. 파일은 `data/samples/parser/` 아래에 저장하며 기존 raw와 SHA-256이 같으면 기존 portable path를 재사용합니다.

```powershell
python scripts/download_samples.py
```

현재 보유한 실제 원본 중 대표 자료의 컨테이너·시트·페이지 구조만 조사하려면 다음 명령을 사용합니다.

```powershell
python scripts/survey_samples.py
```

결과는 `data/audit/parser_structure_report.json`에 저장됩니다. XLSX/XLS는 시트, 병합 셀, 실제 비어 있지 않은 범위, 수식·숫자·날짜 서식을 조사합니다. HWPX는 ZIP/XML, 표·행·셀·중첩 표를, PDF는 페이지 크기·텍스트 블록·이미지·image-only 가능성을 조사합니다. HWP는 OLE/CFB signature와 stream 구조까지만 확인합니다. 구조 fingerprint 결과는 `data/audit/template_families.json`에 저장됩니다. 이 명령은 식단 행/열을 추출하는 parser가 아니며 원본 파일을 수정하지 않습니다.

## Phase 3A Excel parser

대표 Excel 표본 19개만 결정론적으로 처리합니다. 실제 signature를 먼저 검사하므로 `.xls` 이름의 OOXML 파일도 XLSX reader로 읽고, 진짜 BIFF 파일만 `xlrd`로 읽습니다. 원본 workbook은 읽기 전용이며 다시 저장하지 않습니다.

```powershell
python scripts/parse_excel_samples.py
```

처리 단계는 format detection → 공통 `WorkbookGrid` → 실제 사용 범위와 병합 셀 복원 → layout family 검출 → 날짜·식사·메뉴 정규화 → Meal schema 1.0 → validation 순서입니다. 현재 지원 layout family는 다음과 같습니다.

- `date_rows_meal_columns`: 날짜가 행에 있고 아침·점심·저녁이 열인 구조
- `weekday_blocks_meal_columns`: 요일별 여러 메뉴 행과 식사 열 구조
- `meal_rows_weekday_columns`: 식사 행과 요일 열 구조

`high` confidence는 날짜와 식사 header 및 source cell을 직접 식별하고 요일 검증까지 통과한 경우입니다. `medium`은 명시적인 요일 표를 해당 월의 실제 날짜에 확장했지만 메뉴와 source cell은 직접 식별한 경우입니다. 날짜·식사 mapping이 모호한 경우에는 낮은 숫자 confidence를 만들지 않고 unresolved/실패로 남깁니다.

비교용 요일 문자열에는 NFKC Unicode normalization을 적용하므로 호환 한자 `金`도 금요일로 인식합니다. 원본 메뉴와 provenance의 `raw_text`는 정규화하거나 덮어쓰지 않습니다. 월간 식단표로 검출된 문서는 해당 월의 모든 날짜와 `breakfast`·`lunch`·`dinner` slot을 coverage matrix로 대조합니다. 날짜 전체 또는 일부 식사가 없으면 PASS가 될 수 없습니다.

산출물:

- `data/processed/excel_raw_tables/`: 셀 값, 좌표, actual range, 병합 parent를 보존한 중간 표
- `data/processed/samples/excel/`: 문서별 Meal schema 1.0 표본 결과
- `data/processed/excel_layout_profiles.json`: 검출 family와 근거
- `data/processed/excel_sample_results.json`: 19개 문서 상태 요약
- `data/processed/excel_validation_report.json`: record 검증 집계
- `data/processed/excel_golden_validation.json`: 원본에서 직접 확인한 golden fixture 대조 결과

`invalid` record는 향후 production-ready dataset에 포함하면 안 됩니다. 이번 명령은 전체 historical Excel을 다운로드하거나 production 변환하지 않습니다.

Production 공개 gate는 다음 조건을 모두 만족해야 합니다.

```text
PRODUCTION_ELIGIBLE =
  status == PASS
  AND invalid == 0
  AND missing_dates == 0
  AND source_provenance_valid == true
```

PARTIAL과 FAIL 문서는 production dataset에 자동 포함하지 않고 review/unresolved 대상으로 분리합니다. 표본 보고서의 gate에 더해 Phase 3B 생산 gate는 missing meal 0, complete coverage, canonical institution을 요구하며 게시일 연도 추정은 REVIEW로 보냅니다. 고정 regression fixture는 `tests/fixtures/production_gate/cases.json`에 있습니다.

## Phase 3B Excel production

historical audit에서 `inmate`/`mixed`이고 선언 확장자가 XLSX/XLS인 문서만 별도 manifest로 생성합니다. 실제 signature와 extension/content mismatch 판정은 Phase 3A의 동일 core reader가 수행합니다.

```powershell
python scripts/build_production_excel_manifest.py
python scripts/download_production_excel.py
python scripts/parse_production_excel.py
python scripts/validate_production_excel.py
```

검증 근거를 별도 파일로 보관하려면 `python scripts/validate_production_excel.py --output data/production/reports/excel_source_validation.json`을 사용합니다. 이 보고서는 1,204개 원본의 SHA/크기, 전체 signature 분포, record issue 분포와 reader 스타일 호환성 진단을 담습니다. 원본이나 공개 메뉴를 수정하지 않습니다.

- 다운로드는 동시성 1, 기본 1.5초 delay와 기존 retry/backoff를 유지합니다. 검증된 기존 raw/sample은 재사용하고 새 원본은 `data/production/raw/`에 보존합니다. 실패는 `reports/excel_download_failures.jsonl`에 기록하고 다음 문서를 처리합니다.
- 다운로드 checkpoint는 `checkpoints/excel_download.json`, 파싱 checkpoint는 `checkpoints/excel_parse.json`입니다. 기본값은 resume이며 `--limit N`, `--from-checkpoint INDEX`(0부터 시작), `--no-resume`을 지원합니다. 완료한 다운로드 실패를 재시도하려면 `--no-resume`으로 전체 manifest를 재확인하면 정상 파일은 SHA 검증 후 재사용합니다.
- 다운로드 실행 중 manifest 생성/파싱을 동시에 실행하지 마십시오. manifest를 다시 생성할 때는 기존 처리 상태를 보존합니다. 파싱 도중 입력이나 parser core/기관 master가 바뀌면 resume을 거부하며 `--new-run`이 필요합니다.
- 파싱은 `ExcelMealParser.parse_sample()`을 호출하고 원본 SHA·크기를 다시 검증합니다. PASS, invalid 0, complete coverage, missing dates/meals 0, 정상 provenance, canonical 기관, 확정 연도를 만족하는 문서만 READY입니다.
- 제목의 게시일 연도 fallback은 `metadata_year_inferred`와 `period_metadata`에 기록합니다. workbook header/파일명에서 같은 연월을 확인하지 못하면 `YEAR_INFERRED_FROM_PUBLICATION`으로 REVIEW 처리합니다.
- 같은 기관/날짜/식사의 메뉴가 다르면 해당 source 문서 전체를 REVIEW로 격리합니다. 같은 메뉴는 웹 projection에서 한 번만 기록하고 모든 `source_document_ids`를 보존합니다. 새 layout은 실패 또는 후보 보고서로 남기며 adapter를 자동 추가하지 않습니다.
- 결과는 `.staging/{run_id}/`에 작성합니다. manifest, READY/REVIEW/FAILED 파일, schema, 원본 출처, 메뉴, 기관/연월 index를 대조한 뒤 `runs/{run_id}/`로 승격하고 `current.json`만 원자적으로 교체합니다. 이전 run은 삭제하지 않습니다. 미완료 실행과 검증 실패는 기존 pointer를 바꾸지 않으며 기존 publication을 빈 READY 결과로 교체하지 않습니다.
- 게시 도중 중단한 실행은 재개 시 이미 승격된 run을 재검증하여 pointer 게시를 마칩니다. 완료된 parse 재실행은 기존 run 보고서를 반환합니다. 새 version을 생성할 때만 `--new-run`을 지정합니다.

게시된 run에는 `excel_manifest.jsonl`, `metadata.json`, `ready/`, `review/`, `failed/`, `reports/excel_production_report.json`, `web_data/`가 들어 있습니다. `current.json`의 `run_path`가 활성 version을 가리킵니다. 웹 소비자는 해당 run의 `web_data/manifest.json`에서 기관→연도→월을 선택하고 `menus/{institution_id}/{year}/{month:02d}.json`을 읽으면 됩니다. 각 meal은 메뉴와 원본 source reference를 갖고 공식 게시물/다운로드 URL을 제공합니다. 로컬 저장 경로는 공개 JSON에 포함하지 않습니다.

검증된 run의 web_data는 READY projection 원본입니다. frontend 배포에는 아래 Phase 3B.1 bridge로 전체 기관 master와 통계를 추가한 **deploy/web_data**를 사용하십시오. 위 production 명령 자체는 `web/`의 frontend 파일이나 기존 public 데이터를 자동으로 덮어쓰지 않습니다. 보고서의 `production_ready`는 웹에 실린 중복 제거 후 meal 수이며 `ready_source_records`는 READY 문서 record 합계입니다. FORMAT은 선언 확장자 기준으로 집계하고 `actual_formats`, `format_extension_mismatches`에 실제 signature 결과를 별도 기록합니다.

## Phase 3B.1 Web Contract Bridge

frontend 전달은 immutable run을 직접 수정하지 않고 별도 public bundle로 수행합니다.
공식 계약은 [docs/web_data_contract.md](docs/web_data_contract.md)를 참고하십시오.

```powershell
python scripts/build_web_bundle.py --fixtures
python scripts/validate_web_bundle.py
python scripts/sync_web_data.py
python scripts/validate_web_bundle.py --frontend
```

deploy는 `data/production/deploy/web_data/`, sync 대상은 `web/public/web_data/`입니다.
공식 master 55개와 READY availability를 분리하고 MM.json/rich meal/public source를 유지합니다.
W1 mock과 이전 bundle은 `web/tests/fixtures/web_data/`에 보존합니다. sync는 완성된
staging tree를 통째로 승격하며 실패 시 이전 tree를 복구합니다. Windows directory 교체의
두 rename 사이 짧은 경로 부재 가능성과 crash 복구 정책은 계약 문서에 명시했습니다.
build/sync는 동시에 실행하지 마십시오. React adapter 변경은 Antigravity W2 범위입니다.

## Phase 3B.2 Menu Semantic Quality Gate

XLSX의 formula 원문과 유효한 cached 표시값을 분리하고, 명백한 Excel 오류·소계·가격·
단가 metadata·안내 주석을 deterministic rule로 분류합니다. 안전한 trailing metadata는
audit를 남겨 제거하지만 미복구 formula/오류 또는 메뉴를 신뢰할 수 없는 slot은 REVIEW로
격리합니다. coverage를 다시 계산하고 staging public lint가 0건일 때만 새 run을 발행합니다.
상세 정책과 before/after 통계 단위는 [docs/menu_quality_gate.md](docs/menu_quality_gate.md)를 참고하십시오.

```powershell
python scripts/report_menu_quality.py --baseline-only
python scripts/parse_production_excel.py --new-run
python scripts/report_menu_quality.py
python scripts/lint_production_menus.py
python scripts/build_web_bundle.py --fixtures
python scripts/sync_web_data.py
```

기존 다운로드 원본을 그대로 재사용하며 old immutable run은 수정/삭제하지 않습니다.
bridge에도 public menu lint를 적용하며 web schema와 React source는 변경하지 않습니다.

## 데이터 모델과 운영

게시글에는 출처 URL, 실제 상세 URL에서 추출한 `post_id`, 기관, 제목, 공개일, 부서, 연락처와 식단 대상 연월을 기록합니다. 첨부에는 실제 다운로드 URL의 ID, 원래 파일명, 선언 확장자, 응답 MIME, 크기, SHA-256, 다운로드 시각과 portable storage key를 기록합니다. 명확한 확장자/MIME 충돌만 `content_type_mismatch`로 표시하며 `application/x-msdownload` 같은 generic download MIME은 원값을 보존하되 오류로 판정하지 않습니다.

사이트 구조가 바뀌면 먼저 fixture를 새 HTML로 갱신하고 `collector/site_adapter.py`만 수정한 뒤 테스트하십시오. 문서 본문 parser를 추가할 때는 원본을 변경하지 않고 별도 모듈과 별도 가공 데이터 디렉터리를 사용해야 합니다. 게시판 검색 요청 역시 `site_adapter`에 격리되어 있습니다.

## 알려진 제약

- 기관 master는 현재 기관 55개 기준이며 폐지·개편된 과거 기관명은 audit의 미해결 목록을 근거로 별도 alias 또는 비활성 기관 레코드를 보강해야 합니다.
- 페이지네이션 규칙은 어댑터에 격리되어 있지만, 사이트가 암호화된 폼 파라미터만 허용하도록 변경되면 해당 메서드를 갱신해야 합니다.
- 과거 audit 자체는 메타데이터 중심입니다. Excel corpus의 실제 signature와 확장자 일치 결과는 production 보고서에서 확인할 수 있으며 다른 형식의 전체 내용 검증은 별도 단계가 필요합니다.
- Phase 3A는 대표 XLSX/XLS 19개를 검증하며 Phase 3B가 전체 inmate/mixed Excel production 변환을 수행합니다. PDF/HWP/HWPX 본문 parser는 포함하지 않습니다.

## Phase 4A incremental operations

Run `python scripts/daily_update.py` locally, or `--dry-run` to collect and validate
without publishing. Default recent refresh: 10 existing meal posts, bounded by 20
pages; configurable with `--refresh-recent` and settings. Existing historical raw,
catalog, immutable runs, and React source remain separate. See
[operational safety and exit codes](docs/incremental_operations.md).

## Phase 4B static institution locations

`python scripts/enrich_institution_locations.py` collects/caches official marker
evidence and validates location candidates. `--apply` enriches latitude/longitude
and updates the existing public bridge; menu and manifest bytes stay unchanged.
No runtime geocoding or React changes. See [location provenance and review policy](docs/institution_locations.md).

# GitHub deployment preparation (Phase 5A)

Phase 5A prepares a lean repository, static GitHub Pages deployment, and one daily incremental update. It does not authenticate, create a GitHub remote, push, or deploy externally. Follow [GitHub setup, persistent-state classification and scheduling policy](docs/github_deployment.md) and the [operations runbook](docs/operations_runbook.md).

- Only current public READY `web/public/web_data/` is shipped to Pages.
- `data/github/` stores a compressed, validated current operational baseline and small review/health metadata; no historical raw archive or old production runs is committed.
- Daily schedule: 23:37 UTC / 08:37 KST next day; manual runs supported.
- NO_CHANGES creates no commit. Review-only changes preserve small state without redeployment. READY changes pass backend/frontend checks before an allowlisted bot commit and reusable Pages deployment.
- Root/custom-domain and repository-subpath builds use `VITE_BASE_PATH` / Vite `BASE_URL` consistently.
- GitHub schedules can be delayed, and public-repository inactivity for 60 days can disable them. Periodic operator inspection remains necessary.

Local checks: `python -m pytest`, `python scripts/github_state.py validate`, `python scripts/repo_size_audit.py --check`; then `npm ci`, `npm run test`, `npm run build` inside `web`, and `node scripts/verify_web_build.mjs` from the root. A fresh lean checkout must first run `python scripts/github_state.py restore`; never run restore over existing local production.

