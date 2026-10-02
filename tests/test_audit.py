from pathlib import Path

from audit.historical import HistoricalAuditor
from audit.reporting import (
    build_audit_summary,
    select_classification_samples,
    select_parser_samples,
    select_representative_samples,
)
from audit.store import HistoricalAuditStore
from collector.models import Attachment, Post
from config.settings import Settings
from institutions.master import Institution, InstitutionMaster


def master() -> InstitutionMaster:
    return InstitutionMaster([
        Institution(
            institution_id="KR_CORR_TEST_PRISON",
            canonical_name="테스트교도소",
            short_name="테스트교",
            institution_type="prison",
            aliases=["테스트(교)"],
            address="테스트 주소",
            source_url="https://example.test/master",
            active=True,
        )
    ])


def post(post_id: str, extension: str = "xlsx", institution_id: str | None = "KR_CORR_TEST_PRISON") -> Post:
    attachment = Attachment(
        attachment_id=f"a{post_id}",
        original_filename=f"{post_id} 수용자 식단표.{extension}",
        extension=extension,
        download_url=f"https://example.test/a{post_id}/download.do",
        document_role="inmate",
        role_confidence=0.97,
        role_rule="filename_inmate_keyword",
    )
    return Post(
        post_id=post_id,
        institution_name="테스트(교)",
        institution_id=institution_id,
        title=f"2025년 {post_id}월 수용자 식단표",
        published_date="2025-01-01",
        post_url=f"https://example.test/{post_id}",
        attachment_count=1,
        is_meal_plan=True,
        meal_year=2025,
        meal_month=min(int(post_id), 12),
        attachments=[attachment],
    )


def test_historical_store_deduplicates_post_ids(tmp_path: Path) -> None:
    store = HistoricalAuditStore(tmp_path / "historical.jsonl")
    store.commit([post("1"), post("2")])
    replacement = post("1", "pdf")
    store.commit([replacement])
    saved = {item.post_id: item for item in store.load()}
    assert len(saved) == 2
    assert saved["1"].attachments[0].extension == "pdf"


def test_audit_summary_and_representative_samples() -> None:
    posts = [post("1", "xlsx"), post("2", "pdf"), post("3", "hwpx", institution_id=None)]
    summary = build_audit_summary(posts, master())
    assert summary["total_meal_posts"] == 3
    assert summary["total_attachments"] == 3
    assert summary["file_types"]["xlsx"] == 1  # type: ignore[index]
    assert summary["unresolved_institutions"] == {"테스트(교)": 1}
    samples = select_representative_samples(posts, limit=10)
    assert {sample["extension"] for sample in samples} == {"xlsx", "pdf", "hwpx"}
    assert all(sample["selection_reason"] for sample in samples)


def test_parser_samples_filter_roles_and_cover_formats() -> None:
    posts = [post(str(index), extension) for index, extension in enumerate(("xlsx", "xls", "pdf", "hwp", "hwpx"), 1)]
    staff = post("6", "pdf")
    staff.attachments[0].document_role = "staff"
    samples = select_parser_samples(posts + [staff], limit=20)
    assert {sample["extension"] for sample in samples} == {"xlsx", "xls", "pdf", "hwp", "hwpx"}
    assert {sample["document_role"] for sample in samples} == {"inmate"}
    assert all(sample["download_status"] == "pending" for sample in samples)


def test_classification_samples_exclude_plain_inmate_documents() -> None:
    inmate = post("1", "xlsx")
    staff = post("2", "pdf")
    staff.attachments[0].document_role = "staff"
    samples = select_classification_samples([inmate, staff], limit=10)
    assert [(sample["post_id"], sample["document_role"]) for sample in samples] == [("2", "staff")]


class Response:
    def __init__(self, content: bytes) -> None:
        self.content = content


class FakeClient:
    def get(self, url: str):
        return Response(b"initial")

    def post(self, url: str, *, data: dict[str, str]):
        if "/page/" in url:
            return Response(f"page:{url.rsplit('/', 1)[1]}".encode())
        return Response(b"detail")


class FakeAdapter:
    pages = {1: ["1", "2"], 2: ["2", "3"], 3: []}

    def search_list_request(self, html: bytes, start_url: str, page: int, search_word: str):
        return f"https://example.test/page/{page}", {"page": str(page), "srchWrd": search_word}

    def parse_list(self, html: bytes, page_url: str):
        page_number = int(html.decode().split(":")[1])
        return [post(post_id) for post_id in self.pages[page_number]]

    def detail_request(self, list_html: bytes, candidate: Post):
        return candidate.post_url, {}

    def parse_detail(self, html: bytes, candidate: Post):
        return candidate


def test_historical_pagination_and_cross_page_duplicate_prevention(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path,
        start_url="https://example.test/list",
        historical_catalog_path=tmp_path / "audit" / "historical.jsonl",
        audit_checkpoint_path=tmp_path / "audit" / "checkpoint.json",
        audit_failures_path=tmp_path / "audit" / "failures.jsonl",
        request_delay_seconds=0,
        retries=0,
    )
    auditor = HistoricalAuditor(master(), settings)
    auditor.client = FakeClient()  # type: ignore[assignment]
    auditor.adapter = FakeAdapter()  # type: ignore[assignment]

    result = auditor.run(max_pages=3, resume=False)

    assert result.status == "complete"
    assert result.pages_scanned == 3
    assert result.total_posts == 3
    assert len({item.post_id for item in auditor.store.load()}) == 3
    checkpoint = __import__("json").loads((tmp_path / "audit" / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["completed"] is True


def test_historical_resume_starts_at_checkpoint(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path,
        start_url="https://example.test/list",
        historical_catalog_path=tmp_path / "audit" / "historical.jsonl",
        audit_checkpoint_path=tmp_path / "audit" / "checkpoint.json",
        audit_failures_path=tmp_path / "audit" / "failures.jsonl",
        request_delay_seconds=0,
        retries=0,
    )
    settings.audit_checkpoint_path.parent.mkdir(parents=True)
    settings.audit_checkpoint_path.write_text('{"next_page": 2, "completed": false}', encoding="utf-8")
    auditor = HistoricalAuditor(master(), settings)
    auditor.client = FakeClient()  # type: ignore[assignment]
    auditor.adapter = FakeAdapter()  # type: ignore[assignment]

    result = auditor.run(max_pages=3, resume=True)

    assert result.status == "complete"
    assert result.pages_scanned == 2
    assert {item.post_id for item in auditor.store.load()} == {"2", "3"}
