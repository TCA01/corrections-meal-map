# Phase 4B static institution locations

Input remains the existing 55-institution master. Only latitude and longitude are
enriched; IDs, names, original addresses, postal codes, contacts and aliases remain
unchanged. No runtime geocoding, browser address submission, React changes,
scheduler or hosting is added.

## Acquisition and provenance

Run `python scripts/enrich_institution_locations.py` to acquire/cache official pages
and produce candidates, audit, review and coverage reports WITHOUT changing master
or public data. Use `--apply` to apply only accepted coordinates and reuse the
existing 3B.1 bridge build/sync. Cache hits do not call the network again.
The process shares Phase 4A's exclusive lock and requires a valid existing dataset.

Priority is an explicit institution map MARKER on the official corrections.go.kr
directions page. The adapter discovers institution/home/directions links from
official navigation, binds the active directions tab's parent menu to the canonical
institution, and extracts the numeric marker LatLng assignment. A map center alone
is never a coordinate source. Global navigation mentioning every institution does
not establish identity. Original fetched HTML and hashes are retained privately.

For Somang's separate official website, the adapter reads that site's JS URL
definition, then the official directions page's embedded map parameters. It also
reads the linked embedded map HTML to confirm those exact parameters are used by
a marker, not merely a center. Neither JavaScript nor geolocation is executed, and
the iframe is NOT added to the frontend. Its source is recorded as an official
institution embedded map marker, not an independently surveyed coordinate.

Optional `--allow-kakao` enables an address-search fallback ONLY when no official
marker exists. `KAKAO_REST_API_KEY` must be supplied in the environment; never use
an embedded website's public SDK key as a REST key. No keys are saved in cache,
audit, source or public data. Missing key/results stay unresolved. Actual provider
responses, address precision and query are retained and validated. Multiple
candidates are REVIEW. This fallback is not needed when official evidence exists.
See [Kakao address API documentation](https://developers.kakao.com/docs/ko/kakaomap/rest-api).
Kakao commercial/storage terms must be checked before enabling that optional path.

All requests are synchronous/concurrency 1 with an identifying User-Agent, minimum
1.5-second spacing, bounded retries/backoff, rate-limit response handling and disk
cache. The public Nominatim endpoint is NOT used or built into this project.

## Validation and statuses

Strip only physical-address typography, parentheses/postal prefixes and the trailing
mailing PO box from queries. Do not geocode a post office or regional center.
Retain the original address verbatim. Full road name + building number, province
aliases and municipality must agree. Whitespace-only road typography is normalized;
a different street, building or city is REVIEW. Explicit marker identity and full
address precision are required. Numeric finite/range, coarse Korea and regional
envelopes reject obvious foreign/offshore/region mismatches.

These envelopes are rejection filters, NOT authoritative borders or a land polygon.
Accepted points are supported by an official institution marker AND matching full
physical address. No assertion of surveyed gate/entrance accuracy or complete GIS
coastline verification is made; `land_polygon_verified=false` is explicit in audit.

- VERIFIED: explicit official institution marker + validation PASS.
- GEOCODED: optional external address geocoder + validation PASS (not official coords).
- REVIEW: ambiguous/mismatching or duplicate-coordinate evidence; public coords null.
- UNRESOLVED: no safely usable candidate; public coords null.

Audit retains official address, provider/source URL, acquisition timestamp/query,
returned address, raw candidate coordinates, validation and evidence. Public
projection retains existing latitude/longitude fields only, no provider debug.
`location_review.json` contains unresolved/review institutions. Coverage/report
includes availability among the 30 institutions with READY meal data, extrema by
region and duplicate groups. Exact duplicate points are NEVER jittered.
Different official addresses sharing an identical point are withheld for manual
campus/entrance review; identical-address groups are still flagged for inspection.

## Publication and invariant checks

Apply retains original master and exact old public bundles. A durable location
transaction journal permits rollback of master/deploy/frontend on failure or the
next locked enrichment run after a crash. If another writer has changed current,
recovery stops for operator review rather than replacing its publication.
Whole-directory bridge swaps retain the existing brief two-rename path interval.
Only institutions.json may change in a served bundle: menus AND manifest bytes,
current pointer, immutable run hash, READY count, slot count and month count must
remain unchanged. No new production version or historical reparsing is performed.

Files: location_raw/, location_audit.json, location_review.json,
institutions_location_candidate.json, location_report.json,
institutions_before_locations.json and location_backups/ under data/institutions.
The cache/audit/backup is private and is not synced to web/public.
There is no automatic periodic location refresh. Operator review is required after
relocation, address changes, official map changes or shared-coordinate ambiguity.
# Phase 4B.1 — Seoul South address geocoding references

서울남부구치소(금오로 865)는 `37.4771593, 126.8371928`, 서울남부교도소(금오로 867)는 `37.4770251553096, 126.837830132687`로 재평가했습니다. 두 값은 사용자가 제공한 주소 geocoding 참고 결과이며 공식 지도 좌표로 분류하지 않습니다.

`location_status=GEOCODED`, `location_source=official_address_geocoding`으로 기록합니다. 원 provider/조회 URL/조회 시각은 제공되지 않아 별도 추측하지 않았고, API를 호출했다고 기록하지 않습니다. 공식 주소 일치·지역 범위·중복 검사를 통과한 참고값이며 측량/출입구 좌표를 보장하지 않습니다.

공개 master에는 좌표만 변경합니다. 추적 가능한 두 기관 provenance와 이전 중복 marker 증거는 `data/institutions/seoul_south_geocoding.json`에 보관합니다. `scripts/hotfix_seoul_south_locations.py`는 기존 bridge를 호출하고 식단 및 manifest의 전후 해시를 검사합니다. GitHub 압축 운영 상태는 재생성하지 않고 `state.json`의 public bundle hash만 맞춰 최신 수집 상태를 보존합니다.

