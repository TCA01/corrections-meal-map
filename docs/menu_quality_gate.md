# Phase 3B.2 Menu Semantic Quality Gate

정책/parser version: `3B.2`. 공개 web schema `1.0` / contract `3B.1`은 그대로 유지한다.
AI/VLM, 외부 API, 재다운로드, formula 계산/추측 복구는 사용하지 않는다.

## 처리 순서

1. 기존 raw 파일 SHA/크기를 검증한다.
2. XLSX를 formula view와 cached data-only view로 읽는다. 원본은 저장/재계산하지 않는다.
3. `CellData.raw_value`/`formula`는 원래 수식을 보존하고, `display_value`/`text`는 유효한
   cached scalar가 있을 때 그 값을 사용한다. `formula_cache_status`로 resolved/unresolved를 구분한다.
4. 지원 layout에서 menu cell을 추출하고 token으로 나눈다. metadata·formula token도 audit 전에 버리지 않는다.
5. anchored deterministic classifier로 definite non-menu를 분류한다.
6. 안전한 trailing metadata만 제거하고 raw/source coordinate 및 artifact audit를 보존한다.
7. 메뉴가 없거나 completeness를 신뢰할 수 없는 slot은 unresolved로 표시하고 coverage를 다시 계산한다.
8. 새 READY gate 및 staging public lint를 모두 통과한 뒤 새 run/current pointer를 발행한다.

## Formula / Excel error 정책

- Cached 값은 nonempty scalar이고 Excel error type/token, 또 다른 formula, NaN/Infinity가 아니어야 한다.
- None/빈 값/Excel 오류 cache는 복구하지 않는다. 원래 literal 또는 cached 오류를 audit하고 REVIEW로 보낸다.
- 정상 cached 음식명은 메뉴로 사용하고 수식/coordinate/cache status는 내부 record source의
  `formula_cells`에 보관한다. 공식 public source의 7필드에는 추가하지 않는다.
- 메뉴 열의 미해결 수식은 `UNRESOLVED_FORMULA_VALUE`; Excel 오류는 `EXCEL_ERROR_VALUE`다.
  정상 메뉴가 다른 곳에 남더라도 메뉴 손실 가능성이 있어 REVIEW다.
- 인접 수량/가격 calculation 열은 음식 열로 오인하지 않는다. formula 통계는 모든 workbook
  formula가 아니라 **추출에 실제 사용한 sheet/cell의 문서별 unique 개수**다.
- XLS는 xlrd가 제공하는 cached value와 error type을 사용한다. XLS formula 원문 복원은 하지 않는다.

## Definite artifact 분류

`parsers/excel/menu_artifacts.py`가 유일한 규칙 원본이다. parser/gate/public lint가 같은 규칙을 공유한다.

| Category | 범위 |
| --- | --- |
| formula_literal | 정규화된 token이 `=`로 시작 |
| excel_error | #REF!, #VALUE!, #DIV/0!, #N/A 등 정확한 Excel error token/type |
| subtotal | 공백 정규화 후 소계/합계/총계 exact match |
| price | 숫자(천 단위 쉼표/소수 허용) + 원만 있는 token |
| placeholder | 0 / 0.0 계열 또는 `-`만 있는 token |
| cost_metadata | corpus에서 확인된 부식물 단가/예정인원/급식비 등의 정확한 표제·단가 주석 |
| instruction_note | 물량 조절/동일 식군 대체 등 corpus에서 확인된 완전한 안내 문구 |
| other | 예약 항목. 추측을 통한 일반 음식명 blacklist는 만들지 않음 |

계란찜/계란후라이/북어계란국/오징어(원양)/참치(원양산)/딸기잼(주식)은 제거하지 않는다.
`계`, `원`, `주식`, `부식` 같은 substring으로 음식명을 걸러내지 않는다.
정읍의 원본 `4,330원`은 단가 주석 전체로 audit한다. 천 단위 쉼표를 잘못 쪼개
‘330원’이라는 가짜 메뉴 token을 생성하지 않는다. `#DIV/0!`의 slash도 분리하지 않는다.

## SAFE_FILTER와 REVIEW

- 정상 메뉴 뒤의 명백한 metadata suffix는 `excluded_from_menu` action으로 audit한다.
  metadata issue는 info로 남기되 실제 menu/coverage를 재검증해 READY 가능하다.
- artifact-only slot, 메뉴 중간 metadata, Excel 오류, 미해결 formula는 `quarantined`다.
  `source.menu_quality_unresolved=true`로 표시하고 그 slot을 정상 coverage에서 제외한다.
- 빈 메뉴를 임의 생성하지 않는다. 디버그 record에는 empty menu와 invalid status를 남길 수 있지만
  그 문서가 public READY로 발행되는 것은 금지한다. REVIEW는 FAIL과 구분한다.
- audit는 `menu_artifacts` / `menu_quality_issues`에 source_cell, source raw text, 분류,
  action, 날짜/끼니를 기록한다. formula 원문도 내부 provenance에 보존한다.
  public JSON에는 cleaned menu와 기존 canonical public source만 내보낸다.

## READY / publication / bridge

기존 구조·날짜·coverage·provenance gate에 다음을 추가한다.

```text
menu_quality_valid == true
unresolved_formula_values == 0
excel_error_menu_items == 0
unresolved_non_menu_artifacts == 0
all normalized menu items are artifact-free
```

실제 staging web_data 전체 lint가 실패하면 current pointer를 바꾸지 않는다.
3B.1 bridge도 deploy/sync 전후에 lint를 수행한다. version/메뉴 hash/기관 master/통계 검증은 유지한다.
기존 오염된 immutable run은 보존하지만 새 gate 아래에서는 그대로 deploy하지 않는다.

## 실행과 보고서

```powershell
python scripts/report_menu_quality.py --baseline-only
python -m pytest
python scripts/parse_production_excel.py --new-run
python scripts/report_menu_quality.py
python scripts/lint_production_menus.py
python scripts/build_web_bundle.py --fixtures
python scripts/lint_production_menus.py --web-data data/production/deploy/web_data
python scripts/sync_web_data.py
python scripts/lint_production_menus.py --web-data web/public/web_data
python scripts/validate_web_bundle.py --frontend
```

baseline은 `reports/menu_quality_before.json`에 old run ID/hash와 전체 occurrence를 보관한다.
같은 unchanged source에 대한 규칙 정교화 시 scan만 다시 계산하고 hash는 유지한다.
비교 보고서는 `reports/menu_quality_comparison.json`, production 전체 요약은 기존
`reports/excel_production_report.json`의 `menu_quality`에 있다. raw 파일이나 old run은 수정하지 않는다.
기존 parse checkpoint는 새 version의 checkpoint로 바뀌며 old immutable run/checkpoint 정책은 동일하다.

Artifact occurrence는 extracted meal item 단위다. 요일 template의 같은 source cell이 여러
실제 날짜에 쓰이면 날짜별로 각각 센다. SAFE_FILTER excluded 수와 REVIEW quarantined 수는
구분한다. formula recovered/unresolved는 unique consumed source cell 단위이므로 occurrence와 다르다.

## 한계

이 gate는 검증한 definite artifact에 대한 보수적 규칙이지 모든 한국 음식명 여부를 판정하는
분류기가 아니다. 임의의 새 주석 표현은 추가 corpus 검수와 exact rule regression이 필요하다.
cached value의 최신성을 Excel 계산 없이 증명하지 않는다. 원본에 저장된 정상 cache만 사용한다.
기존 unsupported layout, 스타일 reader 예외, 미확정 연도, source scope 구분은 이 단계에서
별도 개선하지 않는다. React·지도·외부 배포도 변경하지 않는다.
