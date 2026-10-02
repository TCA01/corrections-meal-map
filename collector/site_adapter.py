from __future__ import annotations

import re
from datetime import date
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .models import Attachment, Post
from .normalizer import classify_extension, is_meal_plan_title, normalize_space, parse_year_month


class CorrectionsSiteAdapter:
    """All corrections.go.kr-specific HTML and URL knowledge lives here."""

    POST_ID_RE = re.compile(r"/(\d+)/artclView\.do")
    ATTACHMENT_ID_RE = re.compile(r"/(\d+)/(?:download|atchFileDownload)\.do")
    DATE_RE = re.compile(r"20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2}")
    INSTITUTION_RE = re.compile(r"^\s*\[([^\]]*)\]")
    JS_POST_RE = re.compile(r"jf_viewArtcl\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"](\d+)['\"]\s*\)")

    def __init__(self, base_url: str = "https://www.corrections.go.kr") -> None:
        self.base_url = base_url

    def list_request(self, html: str | bytes, start_url: str, page: int) -> tuple[str, dict[str, str] | None]:
        if page == 1:
            return start_url, None
        soup = BeautifulSoup(html, "html.parser")
        form = soup.select_one("form[name='pageForm']")
        data = self._form_data(form)
        data["page"] = str(page)
        return urljoin(start_url, "/policyOpen/corrections/artclList.do"), data

    def search_list_request(
        self,
        html: str | bytes,
        start_url: str,
        page: int,
        search_word: str,
    ) -> tuple[str, dict[str, str]]:
        """Build the board's read-only title-search POST for historical audit."""
        soup = BeautifulSoup(html, "html.parser")
        form = soup.select_one("form[name='pageForm']")
        data = self._form_data(form)
        data.update({"page": str(page), "srchColumn": "title", "srchWrd": search_word})
        return urljoin(start_url, "/policyOpen/corrections/artclList.do"), data

    def detail_request(self, list_html: str | bytes, post: Post) -> tuple[str, dict[str, str]]:
        soup = BeautifulSoup(list_html, "html.parser")
        form = soup.select_one("form[name='viewForm']")
        return post.post_url, self._form_data(form)

    def parse_list(self, html: str | bytes, page_url: str) -> list[Post]:
        soup = BeautifulSoup(html, "html.parser")
        posts: list[Post] = []
        seen: set[str] = set()
        for row in soup.select("table tbody tr"):
            anchor = self._post_anchor(row)
            if anchor is None:
                continue
            href = self._link_target(anchor)
            post_id = self.extract_post_id(href)
            if not post_id or post_id in seen:
                continue
            title = normalize_space(anchor.get_text(" ", strip=True))
            cells = [normalize_space(cell.get_text(" ", strip=True)) for cell in row.select("th, td")]
            published = next((self.normalize_date(x) for x in cells if self.DATE_RE.search(x)), None)
            department = self._department_from_cells(cells)
            institution = self.extract_institution(title)
            year, month = parse_year_month(title, self._year(published))
            posts.append(Post(
                post_id=post_id,
                institution_name=institution,
                title=title,
                published_date=published,
                post_url=self._post_url(href, page_url),
                department=department,
                is_meal_plan=is_meal_plan_title(title),
                meal_year=year,
                meal_month=month,
            ))
            seen.add(post_id)
        return posts

    def parse_detail(self, html: str | bytes, post: Post) -> Post:
        soup = BeautifulSoup(html, "html.parser")
        title_node = soup.select_one("h1, h2, h3, .view-title, .artclViewTitle")
        if title_node and "수용" in title_node.get_text(" ", strip=True):
            post.title = normalize_space(title_node.get_text(" ", strip=True))
        text = normalize_space(soup.get_text(" ", strip=True))
        post.department = self._labeled_value(soup, "담당부서") or post.department
        post.contact = self._labeled_value(soup, "전화번호") or post.contact
        detail_date = self._labeled_value(soup, "작성일")
        if detail_date and self.DATE_RE.search(detail_date):
            post.published_date = self.normalize_date(detail_date)
        institution_node = soup.select_one(".artclViewHead .writer, .institution, .organ")
        if institution_node:
            post.institution_name = normalize_space(institution_node.get_text(" ", strip=True))
        if post.institution_name == "unknown":
            post.institution_name = self.extract_institution(post.title)
        post.attachments = self._attachments(soup, post.post_url)
        post.attachment_count = len(post.attachments)
        post.is_meal_plan = is_meal_plan_title(post.title)
        post.meal_year, post.meal_month = parse_year_month(post.title, self._year(post.published_date))
        return post

    def extract_post_id(self, value: str) -> str | None:
        js_match = self.JS_POST_RE.search(value)
        if js_match:
            return js_match.group(2)
        match = self.POST_ID_RE.search(value)
        if match:
            return match.group(1)
        query = parse_qs(urlparse(value).query)
        for key in ("artclSeq", "articleNo", "nttId"):
            if query.get(key):
                return query[key][0]
        match = re.search(r"(?:artclSeq|articleNo|nttId)[=,'\"\s]+(\d+)", value)
        return match.group(1) if match else None

    def extract_institution(self, title: str) -> str:
        match = self.INSTITUTION_RE.search(title)
        return normalize_space(match.group(1)) if match and match.group(1).strip() else "unknown"

    @staticmethod
    def normalize_date(value: str) -> str | None:
        match = CorrectionsSiteAdapter.DATE_RE.search(value)
        if not match:
            return None
        parts = re.split(r"[.\-/]", match.group())
        return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"

    def _post_anchor(self, row: Tag) -> Tag | None:
        for anchor in row.select("a[href], a[onclick]"):
            if self.extract_post_id(self._link_target(anchor)):
                return anchor
        return None

    @staticmethod
    def _link_target(anchor: Tag) -> str:
        return str(anchor.get("href") or anchor.get("onclick") or "")

    def _post_url(self, target: str, page_url: str) -> str:
        match = self.JS_POST_RE.search(target)
        if match:
            site_id, post_id = match.groups()
            return urljoin(page_url, f"/policyOpen/{site_id}/{post_id}/artclView.do")
        return urljoin(page_url, target)

    def _attachments(self, soup: BeautifulSoup, post_url: str) -> list[Attachment]:
        results: list[Attachment] = []
        seen: set[str] = set()
        for anchor in soup.select("a[href], a[onclick]"):
            target = self._link_target(anchor)
            if "download.do" not in target and "atchFileDownload.do" not in target:
                continue
            url = urljoin(post_url, target)
            attachment_id = self._attachment_id(target) or url
            if attachment_id in seen:
                continue
            # On the live site title is the action label ("다운로드"), while
            # the visible anchor text is the original filename.
            filename = normalize_space(str(anchor.get("data-filename") or anchor.get_text(" ", strip=True) or anchor.get("title")))
            filename = re.sub(r"\s*바로보기\s*$", "", filename).strip() or f"attachment-{attachment_id}"
            results.append(Attachment(
                attachment_id=attachment_id,
                original_filename=filename,
                extension=classify_extension(filename),
                declared_extension=classify_extension(filename),
                download_url=url,
            ))
            seen.add(attachment_id)
        return results

    def _attachment_id(self, value: str) -> str | None:
        match = self.ATTACHMENT_ID_RE.search(value)
        if match:
            return match.group(1)
        query = parse_qs(urlparse(value).query)
        for key in ("fileSeq", "atchFileId", "fileId"):
            if query.get(key):
                return query[key][0]
        return None

    @staticmethod
    def _form_data(form: Tag | None) -> dict[str, str]:
        if form is None:
            return {}
        return {
            str(control.get("name")): str(control.get("value") or "")
            for control in form.select("input[name]")
            if control.get("name")
        }

    @staticmethod
    def _department_from_cells(cells: list[str]) -> str | None:
        for index, value in enumerate(cells):
            if CorrectionsSiteAdapter.DATE_RE.search(value) and index > 0:
                return cells[index - 1] or None
        return None

    @staticmethod
    def _labeled_value(soup: BeautifulSoup, label: str) -> str | None:
        for node in soup.find_all(string=lambda text: text and normalize_space(text) == label):
            parent = node.parent
            if not parent:
                continue
            sibling = parent.find_next_sibling()
            if sibling:
                value = normalize_space(sibling.get_text(" ", strip=True))
                if value:
                    return value
            container = parent.parent
            if container:
                text = normalize_space(container.get_text(" ", strip=True))
                value = text.removeprefix(label).strip(" :")
                if value:
                    return value
        return None

    @staticmethod
    def _year(value: str | None) -> int | None:
        return date.fromisoformat(value).year if value else None

