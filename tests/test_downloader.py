from pathlib import Path

from collector.attachment_downloader import AttachmentDownloader
from collector.models import Attachment, Post


class FakeResponse:
    headers = {"Content-Type": "application/pdf"}

    def iter_content(self, chunk_size: int):
        yield b"same bytes"


class FakeClient:
    def get(self, url: str, *, stream: bool = False):
        return FakeResponse()


def post_with_attachment(attachment_id: str) -> tuple[Post, Attachment]:
    attachment = Attachment(attachment_id, f"{attachment_id}.pdf", "pdf", f"https://example.test/{attachment_id}/download.do")
    post = Post(attachment_id, "테스트교도소", "2026년 9월 수용자 식단표", "2026-09-01", f"https://example.test/{attachment_id}/artclView.do", attachment_count=1, is_meal_plan=True, meal_year=2026, meal_month=9, attachments=[attachment])
    return post, attachment


def test_sha256_duplicate_is_not_stored_twice(tmp_path: Path) -> None:
    downloader = AttachmentDownloader(tmp_path, FakeClient())  # type: ignore[arg-type]
    first_post, first = post_with_attachment("10")
    second_post, second = post_with_attachment("11")
    downloader.download(first_post, first)
    downloader.download(second_post, second)
    assert first.status == "downloaded"
    assert second.status == "duplicate"
    assert first.sha256 == second.sha256
    assert second.duplicate_of == first.local_path
    assert len(list(tmp_path.rglob("*.pdf"))) == 1


def test_catalog_path_is_portable_relative_key(tmp_path: Path) -> None:
    raw_root = tmp_path / "data" / "raw"
    downloader = AttachmentDownloader(raw_root, FakeClient(), storage_root=tmp_path)  # type: ignore[arg-type]
    post, attachment = post_with_attachment("12")
    downloader.download(post, attachment)
    assert attachment.local_path is not None
    assert attachment.local_path.startswith("data/raw/")
    assert not Path(attachment.local_path).is_absolute()
    assert downloader.resolve_storage_path(attachment.local_path).is_file()


def test_missing_catalog_file_does_not_discard_new_download(tmp_path: Path) -> None:
    raw_root = tmp_path / "data" / "raw"
    downloader = AttachmentDownloader(raw_root, FakeClient(), storage_root=tmp_path)  # type: ignore[arg-type]
    old_post, old_attachment = post_with_attachment("13")
    old_attachment.sha256 = "known-hash"
    old_attachment.local_path = "data/raw/missing/meal.pdf"
    old_attachment.status = "downloaded"
    downloader.seed_hashes([old_post])

    new_post, new_attachment = post_with_attachment("13")
    downloader.download(new_post, new_attachment)
    assert new_attachment.status == "downloaded"
    assert new_attachment.duplicate_of is None
    assert downloader.resolve_storage_path(new_attachment.local_path or "").is_file()


def test_generic_download_mime_is_not_a_false_mismatch() -> None:
    assert AttachmentDownloader._mime_mismatch("xlsx", "application/x-msdownload") is False
    assert AttachmentDownloader._mime_mismatch("hwpx", "application/octet-stream") is False
    assert AttachmentDownloader._mime_mismatch("xlsx", "image/png") is True


def test_seed_hashes_repairs_catalog_with_no_canonical_record(tmp_path: Path) -> None:
    raw_root = tmp_path / "data" / "raw"
    raw_file = raw_root / "test" / "2026" / "09" / "meal.pdf"
    raw_file.parent.mkdir(parents=True)
    raw_file.write_bytes(b"same bytes")
    downloader = AttachmentDownloader(raw_root, FakeClient(), storage_root=tmp_path)  # type: ignore[arg-type]
    post, attachment = post_with_attachment("14")
    attachment.sha256 = "a" * 64
    attachment.local_path = raw_file.as_posix()
    attachment.duplicate_of = raw_file.as_posix()
    attachment.status = "duplicate"
    attachment.mime_type = "application/x-msdownload"
    attachment.content_type_mismatch = True

    downloader.seed_hashes([post])

    assert attachment.status == "downloaded"
    assert attachment.duplicate_of is None
    assert attachment.local_path == "data/raw/test/2026/09/meal.pdf"
    assert attachment.content_type_mismatch is False

