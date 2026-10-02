from __future__ import annotations

from copy import deepcopy
import json

import pytest
import requests

from institutions.geocoding import CachedLocationClient, OfficialLocationAdapter, KakaoAddressGeocoder
from institutions.location_validation import validate_location, normalized_address, duplicate_coordinates
from institutions.location_pipeline import enrich_locations, location_report
from production.io import atomic_json
from production.validation import read_json
from production.web_bridge import tree_digest
from test_web_bridge import bridge


INSTITUTION = {"institution_id": "I1", "canonical_name": "서울구치소",
               "address": "경기도 의왕시 안양판교로 143 (포일동) 경기도 군포우체국 사서함 20호",
               "latitude": None, "longitude": None}
CANDIDATE = {"latitude": 37.3963082, "longitude": 126.9878874,
             "returned_address": "경기도 의왕시 안양판교로 143(포일동)",
             "official": True, "institution_identity_verified": True,
             "precision": "institution_marker_or_full_road_address", "provider": "official",
             "source_url": "https://www.corrections.go.kr/corrections/1222/subview.do", "query": "공식 주소"}


def test_valid_coordinate():
    assert validate_location(INSTITUTION, CANDIDATE)["status"] == "PASS"


@pytest.mark.parametrize("latitude,longitude", [(91, 127), (37, 181), (float("nan"), 127), (True, 127), (None, 127)])
def test_invalid_coordinate_range(latitude, longitude):
    candidate = {**CANDIDATE, "latitude": latitude, "longitude": longitude}
    assert "INVALID_COORDINATE_RANGE" in validate_location(INSTITUTION, candidate)["issues"]


@pytest.mark.parametrize("latitude,longitude", [(35.6, 139.7), (40, 127), (37, 123), (30, 127)])
def test_non_korea_or_obvious_offshore_rejected(latitude, longitude):
    result = validate_location(INSTITUTION, {**CANDIDATE, "latitude": latitude, "longitude": longitude})
    assert "OUTSIDE_KOREA_OR_OFFSHORE" in result["issues"]


def test_address_mismatch_is_review():
    result = validate_location(INSTITUTION, {**CANDIDATE, "returned_address": "서울특별시 구로구 금오로 865"})
    assert result["status"] == "REVIEW" and "ADMINISTRATIVE_AREA_MISMATCH" in result["issues"]


def test_same_province_different_city_rejected():
    result = validate_location(INSTITUTION, {**CANDIDATE, "returned_address": "경기도 성남시 안양판교로 143"})
    assert "MUNICIPALITY_MISMATCH" in result["issues"]


def test_same_city_wrong_building_rejected():
    result = validate_location(INSTITUTION, {**CANDIDATE, "returned_address": "경기도 의왕시 안양판교로 144"})
    assert "ROAD_ADDRESS_MISMATCH" in result["issues"]


def test_different_district_and_po_box_cannot_mask_municipality_mismatch():
    institution = {**INSTITUTION, "address": "서울특별시 송파구 정의로 37"}
    candidate = {**CANDIDATE, "latitude": 37.48255, "longitude": 127.115774,
                 "returned_address": "서울특별시 강남구 정의로 37"}
    assert "DISTRICT_MISMATCH" in validate_location(institution, candidate)["issues"]
    candidate["returned_address"] = "경기도 성남시 안양판교로 143 경기도 의왕시 우체국 사서함 20호"
    assert "MUNICIPALITY_MISMATCH" in validate_location(INSTITUTION, candidate)["issues"]


def test_coordinate_wrong_region_rejected():
    result = validate_location(INSTITUTION, {**CANDIDATE, "latitude": 35.1, "longitude": 129.1})
    assert "COORDINATE_REGION_MISMATCH" in result["issues"]


def test_no_city_center_substitution():
    assert validate_location(INSTITUTION, {**CANDIDATE, "precision": "city_center"})["status"] == "REVIEW"


def test_normalization_preserves_physical_address_excludes_po_box():
    assert normalized_address(INSTITUTION["address"]) == "경기도 의왕시 안양판교로 143"
    assert normalized_address("강원특별자치도 속초시 동해대로 4511번길 13 우체국 사서함 2호") == "강원특별자치도 속초시 동해대로4511번길 13"
    assert normalized_address("충청북도 청주시 서원구 청남로 1887번길 49") == "충청북도 청주시 서원구 청남로1887번길 49"


def test_postcode_prefix_and_internal_road_spaces_are_typography_only():
    institution = {**INSTITUTION, "address": "전남광주통합특별시 장흥군 용산면 장흥대로 2667"}
    candidate = {**CANDIDATE, "latitude": 34.6074154, "longitude": 126.908168,
                 "returned_address": "우 59345 전남광주통합특별시 장흥군 용산면 장흥대로 2667"}
    assert validate_location(institution, candidate)["status"] == "PASS"
    institution["address"] = "경상남도 통영시 용남면 용남해안로 277"
    candidate.update(latitude=34.862845, longitude=128.434014, returned_address="경남 통영시 용남 해안로 277")
    assert validate_location(institution, candidate)["status"] == "PASS"


def test_road_substring_does_not_accept_different_road_name():
    result = validate_location(INSTITUTION, {**CANDIDATE, "returned_address": "경기도 의왕시 신안양판교로 143"})
    assert "ROAD_ADDRESS_MISMATCH" in result["issues"]


def test_provider_response_parsing_and_lon_lat_order():
    raw = {"documents": [{"x": "126.9878874", "y": "37.3963082", "address_type": "ROAD_ADDR",
                          "road_address": {"address_name": "경기도 의왕시 안양판교로 143"}}]}
    result = KakaoAddressGeocoder.parse_response(raw, "query")[0]
    assert result["latitude"] == "37.3963082" and result["longitude"] == "126.9878874"
    assert result["official"] is False and validate_location(INSTITUTION, result)["status"] == "PASS"


class Response:
    url = "https://example.test/location"
    content = b"page"
    def raise_for_status(self):
        pass
    def json(self):
        return {"documents": []}


class Session:
    def __init__(self, failures=0):
        self.headers = {}
        self.calls = 0
        self.failures = failures
    def get(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise requests.ConnectionError("fixture network failure")
        return Response()


def test_geocoder_retry_and_backoff(tmp_path):
    session = Session(1)
    waits = []
    client = CachedLocationClient(tmp_path, session=session, sleep=waits.append, clock=lambda: 0)
    client.get("https://example.test/test")
    assert session.calls == 2 and 1 in waits and 1.5 in waits


def test_geocoder_rate_limit_between_distinct_requests(tmp_path):
    waits = []
    client = CachedLocationClient(tmp_path, session=Session(), sleep=waits.append, clock=lambda: 0)
    client.get("https://example.test/1")
    client.get("https://example.test/2")
    assert waits == [1.5]


def test_cache_avoids_repeated_network_request(tmp_path):
    session = Session()
    client = CachedLocationClient(tmp_path, session=session)
    first = client.get("https://example.test/1")
    assert client.get("https://example.test/1") == first and session.calls == 1
    assert json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))["payload"] == "page"


def test_absent_key_never_calls_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    session = Session()
    provider = KakaoAddressGeocoder(CachedLocationClient(tmp_path, session=session))
    results, evidence = provider.locate(INSTITUTION)
    assert not results and evidence["reason"] == "GEOCODER_KEY_NOT_CONFIGURED" and session.calls == 0


def official_html(name="서울구치소", marker=True):
    return f'''<a href="/corrections/1220/subview.do" class="menuNum_1137">{name}</a>
    <a href="/corrections/1222/subview.do" class="k2wiz_GNB_1137">오시는길</a>
    <div id="_contentBuilder">기관주소 경기도 의왕시 안양판교로 143(포일동) 우편주소 군포 사서함</div>
    <script>var center=new kakao.maps.LatLng(37.3963082,126.9878874);
    {"var position=new kakao.maps.LatLng(37.3963082,126.9878874);" if marker else ""}</script>'''


def test_official_marker_parsing_bound_to_institution():
    adapter = OfficialLocationAdapter(None)
    candidate = adapter.parse(official_html(), INSTITUTION, CANDIDATE["source_url"])
    assert candidate["institution_identity_verified"] and validate_location(INSTITUTION, candidate)["status"] == "PASS"


def test_map_center_alone_is_not_invented_marker():
    assert OfficialLocationAdapter(None).parse(official_html(marker=False), INSTITUTION, CANDIDATE["source_url"]) is None


def test_global_navigation_other_institution_cannot_verify():
    candidate = OfficialLocationAdapter(None).parse(official_html("다른교도소"), INSTITUTION, CANDIDATE["source_url"])
    assert candidate["institution_identity_verified"] is False
    assert validate_location(INSTITUTION, candidate)["status"] == "REVIEW"


class OfficialFixture:
    def __init__(self, candidate=None):
        self.candidate = candidate
    def locate(self, *args):
        return deepcopy(self.candidate), {"reason": "fixture"}


def test_unresolved_stays_null_no_invented_coordinate():
    updated, audit, _ = enrich_locations([INSTITUTION], OfficialFixture(), {"I1": "https://example.test"})
    assert updated[0]["latitude"] is None and updated[0]["longitude"] is None
    assert audit[0]["status"] == "UNRESOLVED"


def test_verified_location_audit_non_coordinate_fields_preserved():
    updated, audit, _ = enrich_locations([INSTITUTION], OfficialFixture(CANDIDATE), {"I1": "https://example.test"})
    assert audit[0]["status"] == "VERIFIED" and audit[0]["provider"] == "official"
    assert audit[0]["validation"]["status"] == "PASS" and audit[0]["returned_address"]
    assert {k: v for k, v in updated[0].items() if k not in {"latitude", "longitude"}} == {k: v for k, v in INSTITUTION.items() if k not in {"latitude", "longitude"}}


def test_invalid_candidate_does_not_leak_to_master():
    bad = {**CANDIDATE, "latitude": 45}
    updated, audit, _ = enrich_locations([INSTITUTION], OfficialFixture(bad), {"I1": "https://example.test"})
    assert audit[0]["status"] == "REVIEW" and updated[0]["latitude"] is None
    assert audit[0]["candidates"][0]["latitude"] == 45


def test_duplicate_coordinate_detection_no_jitter():
    rows = [{"institution_id": "A", "latitude": 37, "longitude": 127, "official_address": INSTITUTION["address"]},
            {"institution_id": "B", "latitude": 37, "longitude": 127, "official_address": INSTITUTION["address"]}]
    duplicates = duplicate_coordinates(rows)
    assert duplicates[0]["institution_ids"] == ["A", "B"] and duplicates[0]["same_official_road_address"]
    assert rows[0]["latitude"] == rows[1]["latitude"] == 37


def test_marker_coverage_and_sanity_report():
    _, audit, duplicates = enrich_locations([INSTITUTION], OfficialFixture(CANDIDATE), {"I1": "https://example.test"})
    report = location_report(audit, duplicates, {"I1"})
    assert report["map_ready"] == 1 and report["ready_data_institutions_with_coordinates"] == 1
    assert report["geographic_sanity"]["min_latitude"] == CANDIDATE["latitude"]


def test_public_projection_and_sync_retain_all_menu_hashes(bridge):
    bridge.build()
    bridge.sync()
    before_menus = tree_digest(bridge.deploy_path / "menus")
    before_manifest = (bridge.deploy_path / "manifest.json").read_bytes()
    pointer = (bridge.settings.production_root / "current.json").read_bytes()
    master = read_json(bridge.settings.institutions_path)
    master[0].update(latitude=37.3963082, longitude=126.9878874)
    atomic_json(bridge.settings.institutions_path, master)
    bridge.build()
    bridge.sync()
    public = read_json(bridge.deploy_path / "institutions.json")
    assert public[0]["latitude"] == 37.3963082 and "location_source" not in public[0]
    assert tree_digest(bridge.deploy_path / "menus") == before_menus
    assert tree_digest(bridge.settings.project_root / "web/public/web_data/menus") == before_menus
    assert (bridge.deploy_path / "manifest.json").read_bytes() == before_manifest
    assert (bridge.settings.production_root / "current.json").read_bytes() == pointer


def test_location_apply_transaction_rollback_on_sync_failure(bridge, monkeypatch):
    from institutions.location_pipeline import apply_location_master
    bridge.build()
    bridge.sync()
    master = read_json(bridge.settings.institutions_path)
    updated = deepcopy(master)
    updated[0].update(latitude=37.3963082, longitude=126.9878874)
    deploy = tree_digest(bridge.deploy_path)
    frontend = tree_digest(bridge.settings.project_root / "web/public/web_data")
    monkeypatch.setattr(bridge, "sync", lambda: (_ for _ in ()).throw(ValueError("fixture failed sync")))
    with pytest.raises(ValueError):
        apply_location_master(bridge.settings, bridge, master, updated)
    assert read_json(bridge.settings.institutions_path) == master
    assert tree_digest(bridge.deploy_path) == deploy
    assert tree_digest(bridge.settings.project_root / "web/public/web_data") == frontend
    assert not (bridge.settings.institutions_path.parent / "location_transaction.json").exists()


def test_location_apply_success_retains_menu_manifest_and_pointer(bridge):
    from institutions.location_pipeline import apply_location_master
    bridge.build()
    bridge.sync()
    master = read_json(bridge.settings.institutions_path)
    updated = deepcopy(master)
    updated[0].update(latitude=37.3963082, longitude=126.9878874)
    menus = tree_digest(bridge.deploy_path / "menus")
    pointer = (bridge.settings.production_root / "current.json").read_bytes()
    apply_location_master(bridge.settings, bridge, master, updated)
    assert tree_digest(bridge.deploy_path / "menus") == menus
    assert read_json(bridge.settings.project_root / "web/public/web_data/institutions.json")[0]["latitude"] == 37.3963082
    assert (bridge.settings.production_root / "current.json").read_bytes() == pointer


def test_somang_official_iframe_marker_parsing(tmp_path):
    class Client:
        def get(self, url):
            if "url_define.js" in url:
                payload = "'sub01_05': '/www.contents.asp?id=sub01_05'"
            elif "www.contents" in url:
                payload = '<title>소망교도소 오시는 길</title>주소. 경기도 여주시 북내면 아가페길 140 전화. 031-000-0000 <iframe src="https://api.webchon.com/daum/maps/map.asp?lat=37.368046&amp;lng=127.654240&amp;height=500"></iframe>'
            else:
                payload = 'var geoLatitude = "37.368046"; var geoLongitude = "127.654240"; var markerPosition = new kakao.maps.LatLng(geoLatitude, geoLongitude);'
            return {"payload": payload, "source_url": url, "payload_sha256": "fixture", "retrieved_at": "2026-10-01"}
    institution = {**INSTITUTION, "canonical_name": "소망교도소", "address": "경기도 여주시 북내읍 아가페길 140"}
    home = {"source_url": "https://somangcorrection.org/", "payload": '<script src="/include/js/url_define.js"></script>'}
    candidate, evidence = OfficialLocationAdapter(Client())._somang(institution, home)
    assert candidate["institution_identity_verified"] and validate_location(institution, candidate)["status"] == "PASS"
    assert candidate["provider"] == "official_institution_embedded_map_marker"


def test_duplicate_different_addresses_withheld_not_jittered():
    other = {**INSTITUTION, "institution_id": "I2", "address": INSTITUTION["address"].replace("143", "144")}
    class Official:
        def locate(self, institution, home):
            candidate = deepcopy(CANDIDATE)
            candidate["returned_address"] = institution["address"]
            return candidate, {}
    updated, audit, duplicates = enrich_locations([INSTITUTION, other], Official(), {"I1": "x", "I2": "y"})
    assert all(item["latitude"] is None for item in updated)
    assert all(item["status"] == "REVIEW" for item in audit)
    assert duplicates[0]["latitude"] == CANDIDATE["latitude"]
