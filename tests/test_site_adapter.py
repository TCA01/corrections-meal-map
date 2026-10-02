from pathlib import Path

from collector.site_adapter import CorrectionsSiteAdapter


FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"


def test_list_and_detail_parsing() -> None:
    adapter = CorrectionsSiteAdapter()
    posts = adapter.parse_list((FIXTURES / "list.html").read_text(encoding="utf-8"), "https://www.corrections.go.kr/corrections/2410/subview.do")
    assert len(posts) == 3
    assert posts[0].post_id == "611000"
    assert posts[0].is_meal_plan is True
    post = posts[1]
    assert post.post_id == "610999"
    assert post.post_url == "https://www.corrections.go.kr/policyOpen/corrections/610999/artclView.do"
    assert post.institution_name == "경주(교)"
    assert post.published_date == "2026-09-28"
    assert post.department == "총무과"
    assert post.is_meal_plan is True
    post = adapter.parse_detail((FIXTURES / "detail.html").read_text(encoding="utf-8"), post)
    assert post.institution_name == "경주교도소"
    assert post.contact == "054-740-3100"
    assert post.attachment_count == 1
    assert post.attachments[0].attachment_id == "500001"
    assert post.attachments[0].extension == "xlsx"


def test_extract_id_from_script_style_link() -> None:
    adapter = CorrectionsSiteAdapter()
    assert adapter.extract_post_id("fnView('artclSeq', '610382')") == "610382"
    assert adapter.extract_post_id("javascript:jf_viewArtcl('corrections', '80196');") == "80196"


def test_post_form_requests_are_isolated_in_adapter() -> None:
    adapter = CorrectionsSiteAdapter()
    html = (FIXTURES / "list.html").read_text(encoding="utf-8")
    url, data = adapter.list_request(html, "https://www.corrections.go.kr/corrections/2410/subview.do", 2)
    assert url.endswith("/policyOpen/corrections/artclList.do")
    assert data == {"page": "2", "layout": "fixture-layout"}

