from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Iterable

from .models import MenuItem
from .menu_artifacts import classify_menu_token


MEAL_ALIASES = {
    "breakfast": ("조식", "아침", "아침식사"),
    "lunch": ("중식", "점심", "점심식사"),
    "dinner": ("석식", "저녁", "저녁식사"),
}
WEEKDAYS = {
    "월": 0, "월요일": 0, "月": 0,
    "화": 1, "화요일": 1, "火": 1,
    "수": 2, "수요일": 2, "水": 2,
    "목": 3, "목요일": 3, "木": 3,
    "금": 4, "금요일": 4, "金": 4,
    "토": 5, "토요일": 5, "土": 5,
    "일": 6, "일요일": 6, "日": 6,
}


def compact(value: object) -> str:
    """Normalize only the comparison form; source/raw menu text stays untouched."""
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", "", normalized)


def normalize_meal_type(value: object) -> str | None:
    text = compact(value)
    for normalized, aliases in MEAL_ALIASES.items():
        if any(alias in text for alias in aliases):
            return normalized
    return None


def normalize_weekday(value: object) -> int | None:
    text = compact(value).replace("/", "")
    return WEEKDAYS.get(text)


def days_in_text(value: object) -> list[int]:
    if isinstance(value, datetime):
        return [value.day]
    if isinstance(value, date):
        return [value.day]
    if isinstance(value, (int, float)) and int(value) == value and 1 <= int(value) <= 31:
        return [int(value)]
    text = str(value or "").strip()
    if not text or re.search(r"\d{3,}", text):
        return []
    numbers = [int(number) for number in re.findall(r"(?<!\d)([0-3]?\d)(?:일)?(?!\d)", text)]
    return [number for number in numbers if 1 <= number <= 31]


def normalize_date(value: object, year: int, month: int) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        number = float(value)
        if 1 <= number <= 31 and number.is_integer():
            try:
                return date(year, month, int(number))
            except ValueError:
                return None
        if number >= 60:
            candidate = date(1899, 12, 30) + timedelta(days=int(number))
            return candidate
    text = str(value or "").strip()
    for pattern in (r"(\d{4})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})", r"(\d{1,2})[-./월]\s*(\d{1,2})"):
        match = re.search(pattern, text)
        if not match:
            continue
        values = [int(item) for item in match.groups()]
        y, m, d = values if len(values) == 3 else (year, *values)
        try:
            return date(y, m, d)
        except ValueError:
            return None
    days = days_in_text(value)
    if len(days) == 1:
        try:
            return date(year, month, days[0])
        except ValueError:
            return None
    return None


def dates_for_weekday(year: int, month: int, weekday: int) -> list[date]:
    return [
        date(year, month, day)
        for day in range(1, calendar.monthrange(year, month)[1] + 1)
        if date(year, month, day).weekday() == weekday
    ]


def split_menu_tokens(raw_text: str) -> list[str]:
    text = str(raw_text or "").strip()
    if not text:
        return []
    if text.startswith("=") or ("\n" not in text and "\r" not in text and classify_menu_token(text) is not None):
        return [text]
    # The slash within an Excel error is not a menu separator.
    text = re.sub(r"#DIV/0!|#N/A", lambda match: match.group().replace("/", "\ue000"), text,
                  flags=re.IGNORECASE)
    parts: list[str] = []
    current = []
    depth = 0
    for character in text:
        if character in "([（":
            depth += 1
        elif character in ")]）" and depth:
            depth -= 1
        if depth == 0 and character in {"\n", "\r", "/", ",", "，"}:
            value = "".join(current).strip(" ·•\t")
            if value:
                parts.append(value)
            current = []
        else:
            current.append(character)
    value = "".join(current).strip(" ·•\t")
    if value:
        parts.append(value)
    return [part.replace("\ue000", "/") for part in parts]


def split_menu_text(raw_text: str) -> list[MenuItem]:
    return [MenuItem(name=part, raw_text=part) for part in split_menu_tokens(raw_text)
            if classify_menu_token(part) is None]


def combine_menu_cells(values: Iterable[str]) -> tuple[list[MenuItem], str]:
    raw_values = [value.strip() for value in values if value]
    # Extraction preserves artifacts until the quality stage records an audit
    # decision. The public split_menu_text API only returns clean menu items.
    return ([MenuItem(part, part) for value in raw_values for part in split_menu_tokens(value)], "\n".join(raw_values))
