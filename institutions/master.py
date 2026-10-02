from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup


OFFICIAL_DIRECTORY_URL = "https://www.corrections.go.kr/corrections/1125/subview.do"

INSTITUTION_IDS = {
    "서울구치소": "KR_CORR_SEOUL_DETENTION",
    "안양교도소": "KR_CORR_ANYANG_PRISON",
    "수원구치소": "KR_CORR_SUWON_DETENTION",
    "서울동부구치소": "KR_CORR_SEOUL_EASTERN_DETENTION",
    "인천구치소": "KR_CORR_INCHEON_DETENTION",
    "서울남부구치소": "KR_CORR_SEOUL_SOUTHERN_DETENTION",
    "화성직업훈련교도소": "KR_CORR_HWASEONG_VOCATIONAL_PRISON",
    "여주교도소": "KR_CORR_YEOJU_PRISON",
    "의정부교도소": "KR_CORR_UIJEONGBU_PRISON",
    "서울남부교도소": "KR_CORR_SEOUL_SOUTHERN_PRISON",
    "춘천교도소": "KR_CORR_CHUNCHEON_PRISON",
    "원주교도소": "KR_CORR_WONJU_PRISON",
    "강릉교도소": "KR_CORR_GANGNEUNG_PRISON",
    "영월교도소": "KR_CORR_YEONGWOL_PRISON",
    "강원북부교도소": "KR_CORR_GANGWON_NORTHERN_PRISON",
    "수원구치소평택지소": "KR_CORR_PYEONGTAEK_BRANCH",
    "소망교도소": "KR_CORR_SOMANG_PRIVATE_PRISON",
    "대구교도소": "KR_CORR_DAEGU_PRISON",
    "부산구치소": "KR_CORR_BUSAN_DETENTION",
    "경북북부제1교도소": "KR_CORR_GYEONGBUK_NORTHERN_1_PRISON",
    "부산교도소": "KR_CORR_BUSAN_PRISON",
    "창원교도소": "KR_CORR_CHANGWON_PRISON",
    "진주교도소": "KR_CORR_JINJU_PRISON",
    "포항교도소": "KR_CORR_POHANG_PRISON",
    "대구구치소": "KR_CORR_DAEGU_DETENTION",
    "경북직업훈련교도소": "KR_CORR_GYEONGBUK_VOCATIONAL_PRISON",
    "안동교도소": "KR_CORR_ANDONG_PRISON",
    "경북북부제2교도소": "KR_CORR_GYEONGBUK_NORTHERN_2_PRISON",
    "김천소년교도소": "KR_CORR_GIMCHEON_JUVENILE_PRISON",
    "경북북부제3교도소": "KR_CORR_GYEONGBUK_NORTHERN_3_PRISON",
    "울산구치소": "KR_CORR_ULSAN_DETENTION",
    "경주교도소": "KR_CORR_GYEONGJU_PRISON",
    "통영구치소": "KR_CORR_TONGYEONG_DETENTION",
    "밀양구치소": "KR_CORR_MIRYANG_DETENTION",
    "상주교도소": "KR_CORR_SANGJU_PRISON",
    "거창구치소": "KR_CORR_GEOCHANG_DETENTION",
    "대전교도소": "KR_CORR_DAEJEON_PRISON",
    "천안개방교도소": "KR_CORR_CHEONAN_OPEN_PRISON",
    "청주교도소": "KR_CORR_CHEONGJU_PRISON",
    "천안교도소": "KR_CORR_CHEONAN_PRISON",
    "청주여자교도소": "KR_CORR_CHEONGJU_WOMENS_PRISON",
    "공주교도소": "KR_CORR_GONGJU_PRISON",
    "충주구치소": "KR_CORR_CHUNGJU_DETENTION",
    "홍성교도소": "KR_CORR_HONGSEONG_PRISON",
    "홍성교도소서산지소": "KR_CORR_SEOSAN_BRANCH",
    "대전교도소논산지소": "KR_CORR_NONSAN_BRANCH",
    "광주교도소": "KR_CORR_GWANGJU_PRISON",
    "전주교도소": "KR_CORR_JEONJU_PRISON",
    "순천교도소": "KR_CORR_SUNCHEON_PRISON",
    "목포교도소": "KR_CORR_MOKPO_PRISON",
    "군산교도소": "KR_CORR_GUNSAN_PRISON",
    "제주교도소": "KR_CORR_JEJU_PRISON",
    "장흥교도소": "KR_CORR_JANGHEUNG_PRISON",
    "해남교도소": "KR_CORR_HAENAM_PRISON",
    "정읍교도소": "KR_CORR_JEONGEUP_PRISON",
}

EXTRA_ALIASES = {
    "서울동부구치소": ["서울동(구)", "서울동부구", "성동구치소"],
    "서울남부구치소": ["서울남(구)", "서울남부구"],
    "서울남부교도소": ["서울남(교)", "서울남부교"],
    "강원북부교도소": ["강원(교)", "강원교", "강원북부교"],
    "수원구치소평택지소": ["평택(지)", "평택지", "평택지소", "수원구치소 평택지소"],
    "홍성교도소서산지소": ["서산(지)", "서산지", "서산지소", "홍성교도소 서산지소"],
    "대전교도소논산지소": ["논산(지)", "논산지", "논산지소", "대전교도소 논산지소"],
    "청주여자교도소": ["청주(여)", "청주여", "청주여교", "청주여자교"],
    "경북직업훈련교도소": ["경북(직훈)", "경북직업(교)", "경북직업훈련교"],
    "김천소년교도소": ["김천(소)", "김천소년교"],
    "경북북부제2교도소": ["경북2(교)", "경북2교"],
    "천안개방교도소": ["천안(개)", "천안개방교"],
    "화성직업훈련교도소": ["화성(직)", "화성(직훈)", "화성직업(교)", "화성직업훈련교"],
    # The board used this consistent typo for 통영구치소 over many years.
    "통영구치소": ["총영(구)", "총영구", "통영(구)", "통영구"],
}


@dataclass(frozen=True)
class Institution:
    institution_id: str
    canonical_name: str
    short_name: str
    institution_type: str
    aliases: list[str]
    address: str
    source_url: str
    active: bool
    postal_code: str | None = None
    phone: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class InstitutionResolution:
    source: str
    institution_id: str | None
    canonical_name: str | None
    matched_alias: str | None
    resolved: bool


class InstitutionMaster:
    def __init__(self, institutions: list[Institution]) -> None:
        self.institutions = institutions
        self._by_id = {item.institution_id: item for item in institutions}
        self._aliases: dict[str, Institution] = {}
        for item in institutions:
            for alias in [item.canonical_name, item.short_name, *item.aliases]:
                key = normalize_alias(alias)
                existing = self._aliases.get(key)
                if existing and existing.institution_id != item.institution_id:
                    raise ValueError(f"ambiguous institution alias: {alias}")
                self._aliases[key] = item

    @classmethod
    def load(cls, path: Path) -> "InstitutionMaster":
        values = json.loads(path.read_text(encoding="utf-8"))
        return cls([Institution(**value) for value in values])

    @classmethod
    def from_official_html(cls, html: str | bytes) -> "InstitutionMaster":
        soup = BeautifulSoup(html, "html.parser")
        institutions: list[Institution] = []
        for row in soup.select("table tbody tr"):
            name_node = row.find("th")
            cells = row.find_all("td", recursive=False)
            if name_node is None or len(cells) < 3:
                continue
            raw_name = clean_text(name_node.get_text(" ", strip=True))
            canonical = canonicalize_name(raw_name)
            if "지방교정청" in canonical:
                continue
            institution_id = INSTITUTION_IDS.get(canonical)
            if not institution_id:
                raise ValueError(f"missing stable institution ID for {canonical}")
            address = clean_text(cells[0].get_text(" ", strip=True))
            postal_codes = re.findall(r"\b\d{5}\b", cells[1].get_text(" ", strip=True))
            phone_text = clean_text(cells[2].get_text(" ", strip=True))
            phone = re.search(r"0\d{1,2}-\d{3,4}-\d{4}(?:~\d+)?", phone_text)
            aliases = build_aliases(canonical, raw_name)
            institutions.append(Institution(
                institution_id=institution_id,
                canonical_name=canonical,
                short_name=short_name(canonical),
                institution_type=institution_type(canonical),
                aliases=aliases,
                address=address,
                postal_code=postal_codes[0] if postal_codes else None,
                phone=phone.group(0) if phone else None,
                source_url=OFFICIAL_DIRECTORY_URL,
                active=True,
            ))
        if len(institutions) != 55:
            raise ValueError(f"expected 55 correctional facilities, found {len(institutions)}")
        return cls(institutions)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([asdict(item) for item in self.institutions], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def resolve(self, source: str) -> InstitutionResolution:
        key = normalize_alias(source)
        item = self._aliases.get(key)
        if item is None:
            return InstitutionResolution(source, None, None, None, False)
        return InstitutionResolution(source, item.institution_id, item.canonical_name, source, True)

    def resolve_post(self, source: str, title: str) -> InstitutionResolution:
        resolution = self.resolve(source)
        if resolution.resolved:
            return resolution
        for candidate in re.findall(r"\[([^\]]+)\]", title):
            resolution = self.resolve(candidate)
            if resolution.resolved:
                return InstitutionResolution(source, resolution.institution_id, resolution.canonical_name, candidate, True)
        return InstitutionResolution(source, None, None, None, False)

    def get(self, institution_id: str) -> Institution | None:
        return self._by_id.get(institution_id)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def canonicalize_name(value: str) -> str:
    value = clean_text(value).replace(" ", "")
    value = re.sub(r"\(구\)성동구치소", "", value)
    value = value.replace("(민영)", "")
    return value


def normalize_alias(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"^[\[【](.*?)[\]】]$", r"\1", value)
    return re.sub(r"[\s._-]+", "", value).lower()


def institution_type(name: str) -> str:
    if name == "소망교도소":
        return "private_prison"
    if name.endswith("지소"):
        return "branch"
    if name.endswith("구치소"):
        return "detention_center"
    if name.endswith("교도소"):
        return "prison"
    return "other"


def short_name(name: str) -> str:
    if name.endswith("지소"):
        for location in ("평택", "서산", "논산"):
            if location in name:
                return f"{location}지소"
    if name.endswith("교도소"):
        return f"{name[:-3]}교"
    if name.endswith("구치소"):
        return f"{name[:-3]}구"
    return name


def build_aliases(canonical: str, raw_name: str) -> list[str]:
    aliases = {canonical, raw_name, canonical.replace(" ", "")}
    base = re.sub(r"(?:교도소|구치소)$", "", canonical)
    if canonical.endswith("교도소"):
        aliases.update({f"{base}교", f"{base}(교)"})
    elif canonical.endswith("구치소"):
        aliases.update({f"{base}구", f"{base}(구)"})
    aliases.update(EXTRA_ALIASES.get(canonical, []))
    aliases.discard("")
    return sorted(aliases)
