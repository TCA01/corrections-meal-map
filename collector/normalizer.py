from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

from .models import SUPPORTED_EXTENSIONS


MEAL_PATTERNS = (
    re.compile(r"수용자\s*(?:(?:,|·|/|및)\s*직원)?\s*식단표"),
    re.compile(r"직원\s*(?:,|·|/|및)\s*수용자\s*식단표"),
    re.compile(r"수용자.{0,8}(?:급식|부식물).{0,8}(?:식단표|차림표|메뉴표)"),
    re.compile(r"(?:급식\s*)?식단표.{0,8}수용자"),
)
YEAR_MONTH_PATTERN = re.compile(
    r"(?:(?P<year>20\d{2}|\d{2})\s*[년.\-/]\s*)?(?P<month>1[0-2]|0?[1-9])\s*월"
)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def is_meal_plan_title(title: str) -> bool:
    normalized = normalize_space(title)
    return any(pattern.search(normalized) for pattern in MEAL_PATTERNS)


def parse_year_month(value: str, fallback_year: int | None = None) -> tuple[int | None, int | None]:
    match = YEAR_MONTH_PATTERN.search(normalize_space(value))
    if not match:
        return None, None
    year_text = match.group("year")
    year = int(year_text) if year_text else fallback_year
    if year is not None and year < 100:
        year += 2000
    return year, int(match.group("month"))


def classify_extension(filename_or_url: str) -> str:
    path = unquote(urlparse(filename_or_url).path)
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix if suffix in SUPPORTED_EXTENSIONS else "unknown"


def safe_filename(value: str) -> str:
    value = normalize_space(Path(unquote(value)).name)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return value[:180] or "attachment.bin"


def slugify_institution(value: str) -> str:
    value = normalize_space(value).lower()
    value = re.sub(r"[^0-9a-z가-힣]+", "-", value).strip("-")
    return value or "unknown-institution"

