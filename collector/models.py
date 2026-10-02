from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


SUPPORTED_EXTENSIONS = {"xlsx", "xls", "csv", "pdf", "hwp", "hwpx"}


@dataclass
class Attachment:
    attachment_id: str
    original_filename: str
    extension: str
    download_url: str
    mime_type: str | None = None
    declared_extension: str | None = None
    content_type_mismatch: bool = False
    file_size: int | None = None
    sha256: str | None = None
    downloaded_at: str | None = None
    local_path: str | None = None
    duplicate_of: str | None = None
    status: str = "discovered"
    error: str | None = None
    document_role: str | None = None
    role_confidence: float | None = None
    role_rule: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Post:
    post_id: str
    institution_name: str
    title: str
    published_date: str | None
    post_url: str
    institution_id: str | None = None
    department: str | None = None
    contact: str | None = None
    attachment_count: int = 0
    is_meal_plan: bool = False
    meal_year: int | None = None
    meal_month: int | None = None
    attachments: list[Attachment] = field(default_factory=list)
    collected_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["attachments"] = [item.to_dict() for item in self.attachments]
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Post":
        data = dict(value)
        data["attachments"] = [Attachment(**a) for a in data.get("attachments", [])]
        return cls(**data)

    def validate(self) -> None:
        if not self.post_id or not self.title or not self.post_url:
            raise ValueError("post_id, title and post_url are required")
        if self.published_date:
            date.fromisoformat(self.published_date)
        if self.attachment_count != len(self.attachments):
            raise ValueError(f"attachment_count mismatch for post {self.post_id}")
        for attachment in self.attachments:
            if not attachment.attachment_id or not attachment.download_url:
                raise ValueError(f"invalid attachment in post {self.post_id}")
            if attachment.status == "downloaded" and not attachment.sha256:
                raise ValueError("downloaded attachment must have sha256")

