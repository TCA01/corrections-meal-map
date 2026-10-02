import pytest

from audit.document_roles import classify_document_role


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("10월 수용자 식단표.xlsx", "inmate"),
        ("10월 수용자 식단표(소년수용자).xlsx", "inmate"),
        ("10월 수용자 식단표(일반수용자).xlsx", "inmate"),
        ("10월 직원 식단표.xlsx", "staff"),
        ("직원 및 수용자 식단표.xlsx", "mixed"),
        ("10월 빵과자표.pdf", "supplementary"),
        ("수용자 부식물 차림표.hwpx", "inmate"),
        ("26년 자비구매의약품 코드번호 및 가격표.pdf", "other"),
        ("구매 코드표(남)-26.2.2.pdf", "other"),
        ("2026년 7월 차림표(교도관).pdf", "staff"),
        ("의무교도대원 차림표.pdf", "staff"),
    ],
)
def test_document_role_rules(filename: str, expected: str) -> None:
    result = classify_document_role(filename)
    assert result.role == expected
    assert result.rule
    assert 0 <= result.confidence <= 1


def test_unknown_role_is_not_silently_guessed() -> None:
    result = classify_document_role("첨부자료.bin")
    assert result.role == "unknown"
    assert result.confidence == 0


def test_generic_attachment_stays_unknown_despite_post_context() -> None:
    result = classify_document_role("2026년 9월 알림.pdf", "[창원교] 수용자 식단표 등")
    assert result.role == "unknown"
    assert result.rule == "ambiguous_title_context_inmate"


def test_generic_meal_table_is_not_supplementary() -> None:
    result = classify_document_role("정보공개차림표(26년_6월).pdf")
    assert result.role == "unknown"
    assert result.rule == "generic_meal_table_without_subject"


def test_generic_meal_table_with_staff_sibling_remains_unknown() -> None:
    result = classify_document_role(
        "정보공개차림표(26년_6월).pdf",
        "직원 및 수용자 식단표",
        ["정보공개차림표(26년_6월).pdf", "직원_및_의무교도대원_차림표(26.6).pdf"],
    )
    assert result.role == "unknown"
    assert result.rule == "generic_meal_table_with_staff_sibling"

