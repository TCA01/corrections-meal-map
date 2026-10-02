from pathlib import Path

from audit.migration import migrate_current_catalog
from collector.catalog import CatalogStore
from collector.models import Post
from institutions.master import INSTITUTION_IDS, InstitutionMaster


MASTER_PATH = Path(__file__).resolve().parents[1] / "data" / "institutions" / "institutions.json"


def test_official_master_has_55_active_facilities_and_stable_ids() -> None:
    master = InstitutionMaster.load(MASTER_PATH)
    assert len(master.institutions) == 55
    assert len({item.institution_id for item in master.institutions}) == 55
    assert all(item.active and item.institution_id.startswith("KR_CORR_") for item in master.institutions)
    assert master.resolve("경주교도소").institution_id == INSTITUTION_IDS["경주교도소"]


def test_board_aliases_resolve_to_canonical_institutions() -> None:
    master = InstitutionMaster.load(MASTER_PATH)
    assert master.resolve("경주(교)").institution_id == "KR_CORR_GYEONGJU_PRISON"
    assert master.resolve("경주교").canonical_name == "경주교도소"
    assert master.resolve("서울남(교)").institution_id == "KR_CORR_SEOUL_SOUTHERN_PRISON"
    assert master.resolve("강원(교)").institution_id == "KR_CORR_GANGWON_NORTHERN_PRISON"
    assert master.resolve("청주(여)").institution_id == "KR_CORR_CHEONGJU_WOMENS_PRISON"
    assert master.resolve("경북(직훈)").institution_id == "KR_CORR_GYEONGBUK_VOCATIONAL_PRISON"
    assert master.resolve("화성(직훈)").institution_id == "KR_CORR_HWASEONG_VOCATIONAL_PRISON"
    assert master.resolve("천안(개)").institution_id == "KR_CORR_CHEONAN_OPEN_PRISON"
    assert master.resolve("총영(구)").institution_id == "KR_CORR_TONGYEONG_DETENTION"


def test_unknown_alias_is_explicitly_unresolved() -> None:
    resolution = InstitutionMaster.load(MASTER_PATH).resolve("가상의 교정기관")
    assert resolution.resolved is False
    assert resolution.institution_id is None
    assert resolution.source == "가상의 교정기관"


def test_empty_primary_alias_can_resolve_from_later_title_bracket() -> None:
    resolution = InstitutionMaster.load(MASTER_PATH).resolve_post("unknown", "[] [거창구치소] 10월 수용자 식단표")
    assert resolution.institution_id == "KR_CORR_GEOCHANG_DETENTION"
    assert resolution.matched_alias == "거창구치소"


def test_catalog_migration_adds_id_without_replacing_source_name(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "posts.jsonl")
    source_name = "경주(교)"
    store.commit([
        Post(
            post_id="1",
            institution_name=source_name,
            title="[경주교도소] 9월 수용자 식단표",
            published_date="2026-09-01",
            post_url="https://example.test/post/1",
        )
    ])

    changed, unresolved = migrate_current_catalog(store, InstitutionMaster.load(MASTER_PATH))
    migrated = store.load()[0]

    assert changed == 1
    assert unresolved == []
    assert migrated.institution_name == source_name
    assert migrated.institution_id == "KR_CORR_GYEONGJU_PRISON"

