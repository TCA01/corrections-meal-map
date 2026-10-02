from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from collector.http_client import PoliteHttpClient
from collector.models import Post
from collector.site_adapter import CorrectionsSiteAdapter
from config.settings import Settings
from institutions.master import InstitutionMaster

from .document_roles import classify_document_role
from .store import HistoricalAuditStore


@dataclass(frozen=True)
class HistoricalAuditResult:
    status: str
    pages_scanned: int
    new_posts: int
    total_posts: int
    total_attachments: int
    failure_count: int


class HistoricalAuditor:
    def __init__(self, master: InstitutionMaster, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.master = master
        self.adapter = CorrectionsSiteAdapter()
        self.client = PoliteHttpClient(
            user_agent=self.settings.user_agent,
            timeout=self.settings.timeout_seconds,
            delay=self.settings.request_delay_seconds,
            retries=self.settings.retries,
        )
        self.store = HistoricalAuditStore(self.settings.historical_catalog_path)

    def run(self, *, max_pages: int | None = None, resume: bool = True) -> HistoricalAuditResult:
        max_pages = max_pages or self.settings.historical_max_pages
        existing = self.store.load()
        existing_ids = {post.post_id for post in existing}
        checkpoint_page, checkpoint_completed = self._load_checkpoint_state() if resume else (1, False)
        if checkpoint_completed:
            return HistoricalAuditResult(
                "complete", 0, 0, len(existing), sum(len(post.attachments) for post in existing), 0
            )
        start_page = checkpoint_page
        failure_count = 0
        pages_scanned = 0
        new_count = 0
        completed = False
        try:
            initial = self.client.get(self.settings.start_url)
            initial_html = initial.content
        except Exception as exc:
            self._record_failure("initial_list", self.settings.start_url, exc)
            return HistoricalAuditResult("fatal", 0, 0, len(existing), sum(len(p.attachments) for p in existing), 1)

        previous_signature: tuple[str, ...] | None = None
        for page in range(start_page, max_pages + 1):
            pages_scanned += 1
            url, data = self.adapter.search_list_request(initial_html, self.settings.start_url, page, "식단")
            try:
                response = self.client.post(url, data=data)
                candidates = self.adapter.parse_list(response.content, url)
            except Exception as exc:
                failure_count += 1
                self._record_failure("list", url, exc, page=page)
                # Retry the same page on the next run; never create a silent
                # hole in the historical corpus.
                self._save_checkpoint(page, completed=False)
                break
            signature = tuple(post.post_id for post in candidates)
            if not candidates or signature == previous_signature:
                completed = True
                self._save_checkpoint(page, completed=True)
                break
            previous_signature = signature
            page_posts: list[Post] = []
            page_detail_failed = False
            for candidate in candidates:
                if not candidate.is_meal_plan or candidate.post_id in existing_ids:
                    continue
                try:
                    detail_url, detail_data = self.adapter.detail_request(response.content, candidate)
                    detail = self.client.post(detail_url, data=detail_data)
                    post = self.adapter.parse_detail(detail.content, candidate)
                    resolution = self.master.resolve_post(post.institution_name, post.title)
                    post.institution_id = resolution.institution_id
                    sibling_filenames = [item.original_filename for item in post.attachments]
                    for attachment in post.attachments:
                        role = classify_document_role(attachment.original_filename, post.title, sibling_filenames)
                        attachment.document_role = role.role
                        attachment.role_confidence = role.confidence
                        attachment.role_rule = role.rule
                    page_posts.append(post)
                    existing_ids.add(post.post_id)
                except Exception as exc:
                    failure_count += 1
                    page_detail_failed = True
                    self._record_failure("detail", candidate.post_url, exc, page=page, post_id=candidate.post_id)
            if page_posts:
                self.store.commit(page_posts)
                new_count += len(page_posts)
            self._save_checkpoint(page if page_detail_failed else page + 1, completed=False)
            print(f"AUDIT PAGE {page}: candidates={len(candidates)} new_meal_posts={len(page_posts)} failures={failure_count}")
            if page_detail_failed:
                break

        posts = self.store.load()
        status = "complete" if completed and not failure_count else ("partial" if posts else "fatal")
        return HistoricalAuditResult(
            status=status,
            pages_scanned=pages_scanned,
            new_posts=new_count,
            total_posts=len(posts),
            total_attachments=sum(len(post.attachments) for post in posts),
            failure_count=failure_count,
        )

    def _load_checkpoint_state(self) -> tuple[int, bool]:
        path = self.settings.audit_checkpoint_path
        if not path.exists():
            return 1, False
        value = json.loads(path.read_text(encoding="utf-8"))
        return int(value.get("next_page", 1)), bool(value.get("completed", False))

    def _save_checkpoint(self, next_page: int, *, completed: bool) -> None:
        path = self.settings.audit_checkpoint_path
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "next_page": next_page,
            "completed": completed,
            "updated_at": datetime.now().astimezone().isoformat(),
        }
        pending = path.with_suffix(".pending")
        pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pending.replace(path)

    def _record_failure(
        self,
        stage: str,
        url: str,
        exc: Exception,
        *,
        page: int | None = None,
        post_id: str | None = None,
    ) -> None:
        logging.error("Historical audit %s failure: %s", stage, exc)
        path = self.settings.audit_failures_path
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "occurred_at": datetime.now().astimezone().isoformat(),
            "stage": stage,
            "url": url,
            "page": page,
            "post_id": post_id,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

