# Web Data Contract — Phase 3B.1

상태: canonical backend contract. Phase 3B.2의 [menu quality gate](menu_quality_gate.md)와
production public lint도 deploy/sync에 적용된다. JSON `schema_version`은 `"1.0"`, manifest의
`web_contract_version`은 `"3B.1"`이다. 기존 immutable run은 변경하지 않는다.
dataset_version은 새 bridge 실행 시각이 아니라 current.json이 가리키는 원본 run ID다.

## 파일과 책임

```text
web_data/
  manifest.json                    실제 READY 식단 availability와 통계
  institutions.json               공식 기관 master 55개 전체
  menus/{institution_id}/{YYYY}/{MM}.json
```

월은 정수 1–12지만 **파일명은 반드시 두 자리 MM.json**이다. 7월은 `07.json`이다.
frontend URL 작성은 `String(month).padStart(2, "0")`을 사용한다.
기관 기준정보와 availability는 다르다. master에 있지만 manifest에 없는 기관은
현재 공개할 READY 식단이 없는 기관이지 존재하지 않는 기관이 아니다.

## manifest.json

```json
{
  "schema_version": "1.0",
  "web_contract_version": "3B.1",
  "dataset_version": "<active immutable run ID>",
  "generated_at": "<source report ISO-8601 timestamp with timezone>",
  "institutions": [
    {"institution_id": "<canonical ID>", "available_years": {"2026": [8, 9, 10]}}
  ],
  "stats": {
    "total_institutions": 55,
    "collected_institutions": 33,
    "structured_documents": 525,
    "total_meal_records": 47814,
    "institution_month_files": 524,
    "last_updated": "<same timestamp as generated_at>",
    "data_scope": "excel_ready_only"
  }
}
```

위 숫자는 Phase 3B.1 검수 당시의 예시이며 hardcoded 기대값이 아니다. 현재 값은 active
deploy manifest의 stats를 읽는다. Phase 3B.2 재평가 후 값은 달라질 수 있다. build는 source
report와 실제 bundle을 대조한다. availability row는 institution_id와 available_years만
갖는다. 연도 key는 4자리 문자열, 월 목록은 오름차순 중복 없는 정수 배열이다.
structured_documents는 공개 source로 연결된 READY 문서 수다. total_meal_records는
기관/날짜/식사별 **중복 제거된 meal slot 수**이며 메뉴 항목 수가 아니다.
REVIEW/FAILED와 PDF/HWP/HWPX는 공개 범위에 포함되지 않는다.

## institutions.json

배열이며 공식 master의 ID와 필드 값을 그대로 public projection한다. ID는 유일하다.

| 필드 | 타입 / 정책 |
| --- | --- |
| institution_id | canonical string |
| name | canonical_name을 export한 string |
| short_name | string 또는 null |
| type | institution_type을 export한 string |
| address | 공식 주소 string |
| postal_code, phone | string 또는 null |
| latitude, longitude | 두 필드 모두 number 또는 모두 null |
| source_url | 공식 출처 http/https URL |
| active | boolean |

좌표 null은 허용하며 임의 geocoding/대체 좌표/0,0 변환을 하지 않는다. frontend는
검색/목록에서 기관을 유지하고 지도 마커만 생략한다. 현재 master는 55개 모두 좌표가 null이다.
내부 aliases/canonical_name/institution_type/local storage 필드는 공개하지 않는다.

## 월 파일과 meal slot

```json
{
  "schema_version": "1.0",
  "institution_id": "<canonical ID>",
  "year": 2026,
  "month": 7,
  "days": {
    "2026-07-01": {
      "breakfast": {
        "menu_items": [{"name": "쌀밥", "raw_text": "쌀밥"}],
        "source_document_id": "<post_id>-<attachment_id>",
        "source_document_ids": ["<post_id>-<attachment_id>"],
        "source": "<the full public source object, not a string in actual data>"
      }
    }
  },
  "sources": ["<full public source objects, not strings in actual data>"]
}
```

위 source 표시는 설명용 placeholder다. 실제 shape는 아래 7필드 object다.
days key는 해당 연월 안의 ISO 날짜다. meal type은 breakfast/lunch/dinner만 허용한다.
slot은 배열-only가 아니라 네 필드를 가진 rich object다. menu_items는 비어 있지 않은
배열이며 각 항목은 name/raw_text string을 갖는다. primary ID는 source_document_ids에
포함되고 모든 ID는 sources에 연결되어야 한다. inline source는 primary source object와
동일해야 한다. 같은 메뉴를 가진 여러 문서의 provenance를 모두 유지한다.

READY bundle에 빈 slot을 새로 만들지 않는다. frontend의 없는 날짜/없는 식사/없는 월
조회는 ‘자료 없음’으로 처리하고 다른 날짜의 메뉴나 fixture로 대체하지 않는다.
빈 menu_items 배열은 이 production contract에서 invalid다.

## Canonical public source

```json
{
  "document_id": "123-456",
  "post_id": "123",
  "attachment_id": "456",
  "post_url": "https://example.test/post/123",
  "download_url": "https://example.test/download/456",
  "original_filename": "식단.xlsx",
  "published_date": "2026-06-20"
}
```

정확히 이 7필드를 사용한다. original_filename은 표시 제목, post_url은 기본 ‘원본
게시글 보기’, download_url은 ‘첨부파일 보기’, published_date는 공개일이다.
두 URL은 http/https다. 로컬 경로(local_path/raw_path/storage_root/duplicate_of),
Windows 절대경로, file URL, raw/sample 저장경로는 공개 JSON에 들어가지 않는다.

## Build / sync / validation

프로젝트 가상환경을 활성화한 뒤 실행한다.

```powershell
python scripts/build_web_bundle.py --fixtures
python scripts/validate_web_bundle.py
python scripts/sync_web_data.py
python scripts/validate_web_bundle.py --frontend
python -m pytest
```

build는 active run의 기존 READY projection만 읽고
`data/production/deploy/web_data/`를 만든다. 파싱/다운로드를 하지 않는다.
완성 bundle의 전체 master, index, source 연결, 통계, 버전, 월 경로, mock/local path를
검증한다. 메뉴 tree는 immutable run과 **바이트 단위 hash까지** 일치해야 한다.
build 전후 run tree hash와 current pointer도 확인한다. 검증 결과는 별도
`data/production/reports/web_bridge_build.json` / `web_bridge_sync.json`에 기록한다.

sync는 검증된 deploy tree 전체를 staging에 복사한 뒤 승격한다. 기존 destination에
개별 파일을 덧붙이지 않는다. 메뉴 수/버전뿐 아니라 전체 tree hash를 확인한다.
기존 directory는 백업하고 승격/검증 실패 시 복구한다. process crash 후 다음 실행은
swap journal로 이전 tree를 우선 복구한다. 백업 및 journal을 임의 삭제하지 않는다.
build/sync는 **동시에 실행하지 않는다**. 정상 실행 완료 후 serving path에는 한 bundle만 있다.

**원자성 한계:** Windows/portable filesystem에서 비어 있지 않은 directory를 한 번의
rename으로 교체할 수 없어, old→backup / staging→destination 두 rename을 사용한다.
파일이 섞이거나 일부만 복사된 tree는 공개하지 않지만 두 rename 사이에 경로가 아주
짧게 없을 수 있다. 무중단 외부 배포 보장은 아니다. 예외 rollback 및 crash journal은
지원한다. 엄격한 단일 연산/무중단 배포가 필요하면 W2 이후 serving-layer version pointer
설계가 추가로 필요하다. 이 단계에서는 React/서빙 계층을 변경하지 않는다.

## Mock / cross-contract fixture 정책

- W1 mock 원본은 `web/tests/fixtures/web_data/w1/`에 바이트 동일하게 보존한다.
- 이전 frontend bundle 백업은 `web/tests/fixtures/web_data/backups/`에 남기며
  `web/public/`에는 mock 백업을 두지 않는다.
- production `web/public/web_data/`와 deploy에는 is_mock_fixture=true 파일이 0개다.
- 실제 READY 월 두 개의 cross-contract fixture는
  `web/tests/fixtures/web_contract/web_data/`에 있다. 월 JSON을 축소/변형하지 않고
  master 전체와 두 월의 subset manifest를 제공한다. 여러 item을 가진 세 meal type을 포함한다.
- `web/tests/fixtures/web_contract/fixture_info.json`은 excerpt임을 명시한다.
  subset manifest 통계는 subset의 실제 값이며 production 통계로 사용하지 않는다.
  active 전체 report/menu hash 검증 때문에 이 subset은 sync로 배포할 수 없다.
- fixture 조회에 없는 날짜/월/기관을 missing-data 테스트로 사용한다. 실제 READY에 없는
  빈 식사를 꾸며 넣지 않는다. 기존 frontend mock 기반 테스트/adapter의 W2 변경은 별도다.

기존 production .staging 및 raw 파일은 정리하거나 삭제하지 않는다.
