from pathlib import Path

import requests

from collector.crawler import CollectionRunResult, CorrectionsCrawler
from collector.models import Attachment, Post
from config.settings import Settings


class Response:
    content = b"<html></html>"


class InitialFailureClient:
    def get(self, url: str):
        raise requests.ConnectionError("offline")


class EmptyClient:
    def get(self, url: str):
        return Response()


class EmptyAdapter:
    def list_request(self, html: bytes, start_url: str, page: int):
        return start_url, None

    def parse_list(self, html: bytes, page_url: str):
        return []


class DetailFailureClient(EmptyClient):
    def post(self, url: str, *, data: dict[str, str]):
        raise requests.ConnectionError("detail unavailable")


class OnePostAdapter(EmptyAdapter):
    def parse_list(self, html: bytes, page_url: str):
        return [Post("1", "기관", "수용자 식단표", "2026-09-01", "https://example.test/1", is_meal_plan=True)]

    def detail_request(self, list_html: bytes, post: Post):
        return post.post_url, {}


def settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        start_url="https://example.test/list",
        raw_root=tmp_path / "data" / "raw",
        catalog_path=tmp_path / "data" / "catalog" / "posts.jsonl",
        attachment_history_path=tmp_path / "data" / "catalog" / "attachment_history.jsonl",
        failures_path=tmp_path / "data" / "failures" / "failures.jsonl",
        request_delay_seconds=0,
        retries=0,
    )


def test_initial_list_failure_is_fatal(tmp_path: Path) -> None:
    crawler = CorrectionsCrawler(settings(tmp_path))
    crawler.client = InitialFailureClient()  # type: ignore[assignment]
    result = crawler.collect(dry_run=True)
    assert result.status == "fatal"
    assert result.exit_code == 2
    assert result.posts == []


def test_successful_empty_list_is_success(tmp_path: Path) -> None:
    crawler = CorrectionsCrawler(settings(tmp_path))
    crawler.client = EmptyClient()  # type: ignore[assignment]
    crawler.adapter = EmptyAdapter()  # type: ignore[assignment]
    result = crawler.collect(dry_run=True)
    assert result.status == "success"
    assert result.exit_code == 0
    assert result.posts == []


def test_detail_failure_is_partial_and_collection_continues(tmp_path: Path) -> None:
    crawler = CorrectionsCrawler(settings(tmp_path))
    crawler.client = DetailFailureClient()  # type: ignore[assignment]
    crawler.adapter = OnePostAdapter()  # type: ignore[assignment]
    result = crawler.collect(dry_run=True)
    assert result.status == "partial"
    assert result.exit_code == 1
    assert result.failure_count == 1


def test_recent_refresh_selection() -> None:
    existing = {"1", "2", "3"}
    assert CorrectionsCrawler._should_refresh_existing("1", existing, True, 2, 0) is True
    assert CorrectionsCrawler._should_refresh_existing("2", existing, True, 2, 1) is True
    assert CorrectionsCrawler._should_refresh_existing("3", existing, True, 2, 2) is False
    assert CorrectionsCrawler._should_refresh_existing("new", existing, True, 2, 2) is True
    assert CorrectionsCrawler._should_refresh_existing("3", existing, False, 0, 0) is True


class MultiPageClient:
    def __init__(self) -> None:
        self.list_pages: list[int] = []

    def get(self, url: str):
        response = Response()
        response.content = b"page:1"
        return response

    def post(self, url: str, *, data: dict[str, str]):
        response = Response()
        if "/page/" in url:
            page = int(url.rsplit("/", 1)[1])
            self.list_pages.append(page)
            response.content = f"page:{page}".encode()
        else:
            response.content = b"detail"
        return response


class MultiPageAdapter:
    counts = {1: 3, 2: 4, 3: 4}

    def list_request(self, html: bytes, start_url: str, page: int):
        return (start_url, None) if page == 1 else (f"https://example.test/page/{page}", {})

    def parse_list(self, html: bytes, page_url: str):
        page = int(html.decode().split(":")[1])
        start = sum(self.counts.get(p, 0) for p in range(1, page)) + 1
        return [
            Post(str(index), "기관", f"{index} 수용자 식단표", "2026-09-01", f"https://example.test/{index}", is_meal_plan=True)
            for index in range(start, start + self.counts.get(page, 0))
        ]

    def detail_request(self, list_html: bytes, post: Post):
        return f"https://example.test/detail/{post.post_id}", {}

    def parse_detail(self, html: bytes, post: Post):
        return post


def test_refresh_recent_scans_multiple_pages_for_true_n(tmp_path: Path) -> None:
    crawler = CorrectionsCrawler(settings(tmp_path))
    crawler.client = MultiPageClient()  # type: ignore[assignment]
    crawler.adapter = MultiPageAdapter()  # type: ignore[assignment]
    existing = [
        Post(str(index), "기관", f"{index} 수용자 식단표", "2026-09-01", f"https://example.test/{index}")
        for index in range(1, 12)
    ]
    crawler.catalog.commit(existing)

    result = crawler.collect(pages=1, latest_only=True, refresh_recent=10, dry_run=True)

    assert result.status == "success"
    assert len(result.posts) == 10
    assert [post.post_id for post in result.posts] == [str(index) for index in range(1, 11)]
    assert crawler.client.list_pages == [2, 3]  # type: ignore[attr-defined]


class NewPostDoesNotCountAdapter(MultiPageAdapter):
    def parse_list(self, html: bytes, page_url: str):
        page = int(html.decode().split(":")[1])
        ids = ["new", "1"] if page == 1 else (["2"] if page == 2 else [])
        return [
            Post(post_id, "기관", f"{post_id} 수용자 식단표", "2026-09-01", f"https://example.test/{post_id}", is_meal_plan=True)
            for post_id in ids
        ]


def test_new_posts_do_not_consume_recent_refresh_target(tmp_path: Path) -> None:
    crawler = CorrectionsCrawler(settings(tmp_path))
    crawler.client = MultiPageClient()  # type: ignore[assignment]
    crawler.adapter = NewPostDoesNotCountAdapter()  # type: ignore[assignment]
    crawler.catalog.commit([
        Post(post_id, "기관", f"{post_id} 수용자 식단표", "2026-09-01", f"https://example.test/{post_id}")
        for post_id in ("1", "2")
    ])

    result = crawler.collect(pages=1, latest_only=True, refresh_recent=2, dry_run=True)

    assert [post.post_id for post in result.posts] == ["new", "1", "2"]
    assert crawler.client.list_pages == [2]  # type: ignore[attr-defined]


class PartialAdapter(OnePostAdapter):
    def parse_list(self, html: bytes, page_url: str):
        return [
            Post("1", "기관", "1 수용자 식단표", "2026-09-01", "https://example.test/1", is_meal_plan=True),
            Post("2", "기관", "2 수용자 식단표", "2026-09-01", "https://example.test/2", is_meal_plan=True),
        ]

    def parse_detail(self, html: bytes, post: Post):
        attachment_id = f"{post.post_id}0"
        post.attachments = [Attachment(attachment_id, f"{post.post_id}.pdf", "pdf", f"https://example.test/{attachment_id}/download.do")]
        post.attachment_count = 1
        return post


class PartialDownloader:
    def seed_hashes(self, posts: list[Post]) -> None:
        pass

    def download(self, post: Post, attachment: Attachment) -> Attachment:
        if post.post_id == "1":
            attachment.status = "failed"
            attachment.error = "timeout"
        else:
            attachment.status = "downloaded"
            attachment.sha256 = "c" * 64
            attachment.local_path = "data/raw/test/2026/09/2-new.pdf"
        return attachment


def existing_post(post_id: str, sha: str) -> Post:
    attachment_id = f"{post_id}0"
    attachment = Attachment(
        attachment_id,
        f"{post_id}.pdf",
        "pdf",
        f"https://example.test/{attachment_id}/download.do",
        sha256=sha,
        local_path=f"data/raw/test/2026/09/{post_id}.pdf",
        status="downloaded",
    )
    return Post(post_id, "기관", f"{post_id} 수용자 식단표", "2026-09-01", f"https://example.test/{post_id}", attachment_count=1, attachments=[attachment])


def test_partial_run_preserves_failed_canonical_and_commits_other_success(tmp_path: Path) -> None:
    crawler = CorrectionsCrawler(settings(tmp_path))
    crawler.client = MultiPageClient()  # type: ignore[assignment]
    crawler.adapter = PartialAdapter()  # type: ignore[assignment]
    crawler.downloader = PartialDownloader()  # type: ignore[assignment]
    crawler.catalog.commit([existing_post("1", "a" * 64), existing_post("2", "b" * 64)])

    result = crawler.collect(pages=1)

    saved = {post.post_id: post for post in crawler.catalog.load()}
    assert result.status == "partial"
    assert saved["1"].attachments[0].status == "downloaded"
    assert saved["1"].attachments[0].sha256 == "a" * 64
    assert saved["2"].attachments[0].sha256 == "c" * 64
    assert "timeout" in crawler.settings.failures_path.read_text(encoding="utf-8")
    history = crawler.settings.attachment_history_path.read_text(encoding="utf-8")
    assert history.count("\n") == 1


def test_run_result_exit_codes() -> None:
    assert CollectionRunResult([], "success").exit_code == 0
    assert CollectionRunResult([], "partial").exit_code == 1
    assert CollectionRunResult([], "fatal").exit_code == 2
