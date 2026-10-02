import json
from pathlib import Path

from audit.reporting import write_json
from audit.sample_downloader import ParserSampleDownloader
from audit.store import HistoricalAuditStore
from collector.models import Attachment, Post
from config.settings import Settings


class FakeResponse:
    headers = {"Content-Type": "application/pdf"}

    def iter_content(self, chunk_size: int):
        yield b"identical sample bytes"


class FakeClient:
    def get(self, url: str, *, stream: bool = False):
        return FakeResponse()


def sample_post(post_id: str) -> Post:
    attachment = Attachment(
        attachment_id=f"a{post_id}",
        original_filename=f"meal-{post_id}.pdf",
        extension="pdf",
        download_url=f"https://example.test/{post_id}.pdf",
        document_role="inmate",
    )
    return Post(
        post_id=post_id,
        institution_name="테스트(교)",
        institution_id="KR_CORR_TEST",
        title="수용자 식단표",
        published_date="2026-01-01",
        post_url=f"https://example.test/{post_id}",
        attachment_count=1,
        meal_year=2026,
        meal_month=1,
        attachments=[attachment],
    )


def test_sample_downloader_updates_manifest_and_reuses_sha(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path,
        raw_root=tmp_path / "data" / "raw",
        catalog_path=tmp_path / "data" / "catalog" / "posts.jsonl",
        attachment_history_path=tmp_path / "data" / "catalog" / "history.jsonl",
        historical_catalog_path=tmp_path / "data" / "audit" / "historical.jsonl",
        parser_samples_path=tmp_path / "data" / "audit" / "parser_samples.json",
        sample_raw_root=tmp_path / "data" / "samples" / "parser",
        sample_download_failures_path=tmp_path / "data" / "audit" / "download_failures.jsonl",
        request_delay_seconds=0,
        retries=0,
    )
    posts = [sample_post("1"), sample_post("2")]
    HistoricalAuditStore(settings.historical_catalog_path).commit(posts)
    manifest = [
        {
            "post_id": post.post_id,
            "attachment_id": post.attachments[0].attachment_id,
            "filename": post.attachments[0].original_filename,
            "extension": "pdf",
            "download_url": post.attachments[0].download_url,
            "download_status": "pending",
            "sha256": None,
            "local_path": None,
            "file_size": None,
        }
        for post in posts
    ]
    write_json(settings.parser_samples_path, manifest)

    result = ParserSampleDownloader(settings, FakeClient()).run()  # type: ignore[arg-type]
    saved = json.loads(settings.parser_samples_path.read_text(encoding="utf-8"))

    assert result.success == 1
    assert result.deduplicated == 1
    assert result.failed == 0
    assert saved[0]["sha256"] == saved[1]["sha256"]
    assert saved[0]["local_path"] == saved[1]["local_path"]
    assert len(list(settings.sample_raw_root.rglob("*.pdf"))) == 1
