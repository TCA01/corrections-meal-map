import pytest

from collector.normalizer import classify_extension, is_meal_plan_title, parse_year_month


@pytest.mark.parametrize(
    ("filename", "fallback", "expected"),
    [
        ("2026년 9월 수용자 식단표.xlsx", None, (2026, 9)),
        ("2026.9월수용자식단표.hwpx", None, (2026, 9)),
        ("9월 수용자 식단표.pdf", 2025, (2025, 9)),
        ("26년 3월 수용자 식단표.hwp", None, (2026, 3)),
    ],
)
def test_parse_year_month(filename: str, fallback: int | None, expected: tuple[int | None, int | None]) -> None:
    assert parse_year_month(filename, fallback) == expected


@pytest.mark.parametrize("extension", ["xlsx", "xls", "csv", "pdf", "hwp", "hwpx"])
def test_supported_extensions(extension: str) -> None:
    assert classify_extension(f"meal.{extension.upper()}") == extension


def test_unknown_extension_is_retained_as_unknown() -> None:
    assert classify_extension("meal.zip") == "unknown"


def test_title_variants() -> None:
    assert is_meal_plan_title("수용자 식단표")
    assert is_meal_plan_title("수용자식단표")
    assert is_meal_plan_title("식단표(직원, 수용자)")
    assert not is_meal_plan_title("직원 식단표")


@pytest.mark.parametrize(
    "title",
    [
        "[청주(여)] 청주여 10월 수용자,직원 식단표, 빵,과자 일정표",
        "수용자, 직원 식단표",
        "수용자 및 직원 식단표",
        "직원 및 수용자 식단표",
        "직원·수용자 식단표",
        "직원,수용자 식단표",
    ],
)
def test_mixed_inmate_staff_title_variants(title: str) -> None:
    assert is_meal_plan_title(title)


@pytest.mark.parametrize("title", ["직원 식단표", "개인정보 처리내역"])
def test_non_inmate_titles_are_not_meal_plans(title: str) -> None:
    assert not is_meal_plan_title(title)

