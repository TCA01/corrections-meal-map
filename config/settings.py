from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    start_url: str = "https://www.corrections.go.kr/corrections/2410/subview.do"
    raw_root: Path = PROJECT_ROOT / "data" / "raw"
    catalog_path: Path = PROJECT_ROOT / "data" / "catalog" / "posts.jsonl"
    attachment_history_path: Path = PROJECT_ROOT / "data" / "catalog" / "attachment_history.jsonl"
    failures_path: Path = PROJECT_ROOT / "data" / "failures" / "failures.jsonl"
    institutions_path: Path = PROJECT_ROOT / "data" / "institutions" / "institutions.json"
    historical_catalog_path: Path = PROJECT_ROOT / "data" / "audit" / "historical_posts.jsonl"
    audit_checkpoint_path: Path = PROJECT_ROOT / "data" / "audit" / "checkpoint.json"
    audit_failures_path: Path = PROJECT_ROOT / "data" / "audit" / "failures.jsonl"
    parser_samples_path: Path = PROJECT_ROOT / "data" / "audit" / "parser_samples.json"
    classification_samples_path: Path = PROJECT_ROOT / "data" / "audit" / "classification_samples.json"
    sample_raw_root: Path = PROJECT_ROOT / "data" / "samples" / "parser"
    sample_download_failures_path: Path = PROJECT_ROOT / "data" / "audit" / "sample_download_failures.jsonl"
    production_root: Path = PROJECT_ROOT / "data" / "production"
    production_manifest_path: Path = PROJECT_ROOT / "data" / "production" / "excel_manifest.jsonl"
    production_download_checkpoint_path: Path = PROJECT_ROOT / "data" / "production" / "checkpoints" / "excel_download.json"
    production_parse_checkpoint_path: Path = PROJECT_ROOT / "data" / "production" / "checkpoints" / "excel_parse.json"
    production_raw_root: Path = PROJECT_ROOT / "data" / "production" / "raw"
    user_agent: str = "CorrectionsMealDataMap/0.1 (+public-data research; respectful crawler)"
    timeout_seconds: float = 30.0
    request_delay_seconds: float = 1.5
    retries: int = 3
    refresh_max_pages: int = 20
    historical_max_pages: int = 400
    ops_refresh_recent: int = 10
    ops_lock_stale_seconds: int = 21600

