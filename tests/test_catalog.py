import json
from pathlib import Path

import pytest

from collector.catalog import CatalogStore
from collector.models import Attachment, Post


def make_post(post_id: str = "1") -> Post:
    attachment = Attachment(
        attachment_id="10",
        original_filename="meal.pdf",
        extension="pdf",
        download_url="https://example.test/10/download.do",
        sha256="a" * 64,
        local_path="data/raw/test/2026/09/meal.pdf",
        status="downloaded",
    )
    return Post(
        post_id=post_id,
        institution_name="테스트교도소",
        title="2026년 9월 수용자 식단표",
        published_date="2026-09-01",
        post_url=f"https://example.test/{post_id}/artclView.do",
        attachment_count=1,
        attachments=[attachment],
    )


def test_catalog_round_trip(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "posts.jsonl")
    store.commit([make_post()])
    assert store.load()[0].attachments[0].sha256 == "a" * 64


def test_invalid_update_never_overwrites_good_catalog(tmp_path: Path) -> None:
    path = tmp_path / "posts.jsonl"
    store = CatalogStore(path)
    store.commit([make_post()])
    before = path.read_bytes()
    invalid = make_post("2")
    invalid.attachment_count = 2
    with pytest.raises(ValueError):
        store.commit([invalid])
    assert path.read_bytes() == before


def test_duplicate_post_ids_are_merged(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "posts.jsonl")
    first = make_post()
    store.commit([first])
    updated = make_post()
    updated.title = "수정된 수용자 식단표"
    store.commit([updated])
    assert len(store.load()) == 1
    assert store.load()[0].title == updated.title


def test_refresh_preserves_canonical_download_metadata(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "posts.jsonl")
    canonical = make_post()
    canonical.attachments[0].downloaded_at = "2026-09-01T00:00:00+09:00"
    store.commit([canonical])

    refreshed = make_post()
    refreshed.title = "새로 확인한 제목"
    refreshed.attachments[0].status = "duplicate"
    refreshed.attachments[0].duplicate_of = canonical.attachments[0].local_path
    refreshed.attachments[0].downloaded_at = "2026-09-02T00:00:00+09:00"
    store.commit([refreshed])

    saved = store.load()[0]
    assert saved.title == "새로 확인한 제목"
    assert saved.attachments[0].status == "downloaded"
    assert saved.attachments[0].duplicate_of is None
    assert saved.attachments[0].downloaded_at == "2026-09-01T00:00:00+09:00"


def test_failed_refresh_preserves_existing_attachment(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "posts.jsonl")
    canonical = make_post()
    store.commit([canonical])
    failed = make_post()
    failed.attachments[0].status = "failed"
    failed.attachments[0].sha256 = None
    failed.attachments[0].local_path = None
    failed.attachments[0].error = "timeout"

    store.commit([failed])

    saved = store.load()[0].attachments[0]
    assert saved.status == "downloaded"
    assert saved.sha256 == "a" * 64
    assert saved.local_path == "data/raw/test/2026/09/meal.pdf"
    assert not store.history_path.exists()


def test_changed_attachment_appends_one_history_event(tmp_path: Path) -> None:
    history = tmp_path / "attachment_history.jsonl"
    store = CatalogStore(tmp_path / "posts.jsonl", history)
    store.commit([make_post()])
    changed = make_post()
    changed.attachments[0].sha256 = "b" * 64
    changed.attachments[0].local_path = "data/raw/test/2026/09/meal-2.pdf"
    changed.attachments[0].original_filename = "meal-updated.pdf"

    store.commit([changed])
    store.commit([changed])

    saved = store.load()[0].attachments[0]
    records = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()]
    assert saved.sha256 == "b" * 64
    assert len(records) == 1
    assert records[0]["old_sha256"] == "a" * 64
    assert records[0]["new_sha256"] == "b" * 64
    assert records[0]["old_local_path"].endswith("meal.pdf")
    assert records[0]["new_local_path"].endswith("meal-2.pdf")

