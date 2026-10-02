"""Offline acquisition adapters. Never imported or called by frontend runtime."""
from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from production.io import atomic_json
from .location_validation import normalized_address


def timestamp():
    return datetime.now().astimezone().isoformat()


class CachedLocationClient:
    """One synchronous client, ≥1.5-second spacing including each retry, disk cache."""
    def __init__(self, cache_root, *, delay=1.5, retries=2, session=None, clock=time.monotonic, sleep=time.sleep):
        self.cache_root = cache_root
        self.delay = max(1.5, delay)
        self.retries = retries
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = "CorrectionsMealDataMap/4B (one-time official institution location audit)"
        self.clock, self.sleep = clock, sleep
        self.last_request = None

    def get(self, url, *, params=None, headers=None, json_response=False):
        import json
        key = hashlib.sha256((url + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
        cache = self.cache_root / f"{key}.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        for attempt in range(self.retries + 1):
            if self.last_request is not None:
                self.sleep(max(0, self.delay - (self.clock() - self.last_request)))
            self.last_request = self.clock()
            try:
                response = self.session.get(url, params=params, headers=headers, timeout=30)
                response.raise_for_status()
                value = response.json() if json_response else response.content.decode("utf-8", errors="replace")
                result = {"source_url": response.url, "retrieved_at": timestamp(), "payload": value,
                          "payload_sha256": hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()}
                atomic_json(cache, result)
                return result
            except requests.RequestException as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                if attempt == self.retries or status in {400, 401, 403, 404}:
                    raise
                retry_after = getattr(getattr(error, "response", None), "headers", {}).get("Retry-After", "0")
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = 0
                self.sleep(min(60, max(2 ** attempt, wait)))


class OfficialLocationAdapter:
    provider = "official_institution_map_marker"
    directory_url = "https://www.corrections.go.kr/corrections/1125/subview.do"

    def __init__(self, client):
        self.client = client

    def institution_links(self, html, master):
        soup = BeautifulSoup(html, "html.parser")
        result = {}
        for anchor in soup.select("a[href]"):
            text = anchor.get_text(" ", strip=True).replace(" ", "")
            for item in master:
                name = item["canonical_name"]
                if text == name or text.startswith(name + "("):
                    result.setdefault(item["institution_id"], urljoin(self.directory_url, anchor["href"]))
        return result

    def directions_url(self, html, page_url):
        soup = BeautifulSoup(html, "html.parser")
        urls = [urljoin(page_url, a["href"]) for a in soup.select("a[href]")
                if a.get_text(" ", strip=True) == "오시는길"]
        return next((u for u in urls if urlparse(u).hostname == urlparse(page_url).hostname), None)

    def parse(self, html, institution, source_url):
        soup = BeautifulSoup(html, "html.parser")
        # Only an explicit marker assignment; never use a map center as a facility coordinate.
        scripts = "\n".join(s.get_text() for s in soup.select("script") if not s.get("src"))
        points = re.findall(r"(?:var\s+)?position\s*=\s*new\s+(?:kakao|daum)\.maps\.LatLng\(\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\)", scripts)
        pairs = {(float(lat), float(lon)) for lat, lon in points}
        if len(pairs) != 1:
            return None
        # The page navigation contains every facility; identity requires the active
        # breadcrumb/menu link to point back to this directions page, not a global name hit.
        same_page = [a for a in soup.select("a[href]") if urljoin(source_url, a["href"]) == source_url]
        groups = {cls for a in same_page for cls in a.get("class", []) if re.fullmatch(r"k2wiz_GNB_\d+", cls)}
        parent_menu_classes = {"menuNum_" + group.rsplit("_", 1)[1] for group in groups}
        linked_names = [a.get_text(" ", strip=True).replace(" ", "") for a in soup.select("a[href]")
                        if (parent_menu_classes | groups) & set(a.get("class", []))]
        identity = any(name == institution["canonical_name"] or name.startswith(institution["canonical_name"] + "(")
                       for name in linked_names)
        content = soup.select_one("#_contentBuilder") or soup
        text = content.get_text(" ", strip=True)
        match = re.search(r"기관\s*주소\s*(.*?)(?:우편\s*주소|문의|교통편)", text)
        returned = match.group(1).strip() if match else ""
        lat, lon = next(iter(pairs))
        return {"latitude": lat, "longitude": lon, "returned_address": returned,
                "source_url": source_url, "provider": self.provider, "official": True,
                "institution_identity_verified": identity,
                "precision": "institution_marker_or_full_road_address",
                "evidence": "explicit_position_marker_LatLng", "query": normalized_address(institution["address"])}

    def locate(self, institution, home):
        record = self.client.get(home)
        if urlparse(record["source_url"]).hostname in {"somangcorrection.org", "www.somangcorrection.org"}:
            return self._somang(institution, record)
        directions = self.directions_url(record["payload"], record["source_url"])
        if not directions:
            return None, {"home_url": home, "reason": "OFFICIAL_DIRECTIONS_NOT_FOUND"}
        page = self.client.get(directions)
        candidate = self.parse(page["payload"], institution, page["source_url"])
        return candidate, {"home_url": home, "directions_url": page["source_url"],
                           "page_sha256": page["payload_sha256"], "retrieved_at": page["retrieved_at"],
                           "reason": None if candidate else "NO_UNAMBIGUOUS_OFFICIAL_MARKER"}

    def _somang(self, institution, home):
        # Resolve the site's own JS URL definition, without executing JavaScript.
        soup = BeautifulSoup(home["payload"], "html.parser")
        source = next((s.get("src") for s in soup.select("script[src]") if "/include/js/url_define.js" in s["src"]), None)
        if not source:
            return None, {"reason": "OFFICIAL_DIRECTIONS_NOT_FOUND"}
        definitions = self.client.get(urljoin(home["source_url"], source))
        match = re.search(r"['\"]sub01_05['\"]\s*:\s*['\"]([^'\"]+)['\"]", definitions["payload"])
        if not match:
            return None, {"reason": "OFFICIAL_DIRECTIONS_NOT_FOUND"}
        directions = urljoin(home["source_url"], match.group(1))
        if urlparse(directions).hostname != urlparse(home["source_url"]).hostname:
            return None, {"reason": "UNTRUSTED_DIRECTIONS_HOST"}
        page = self.client.get(directions)
        soup = BeautifulSoup(page["payload"], "html.parser")
        frames = [urljoin(directions, f["src"]) for f in soup.select("iframe[src]")
                  if urlparse(urljoin(directions, f["src"])).hostname == "api.webchon.com"
                  and urlparse(f["src"]).path == "/daum/maps/map.asp"]
        if len(frames) != 1:
            return None, {"reason": "NO_UNAMBIGUOUS_OFFICIAL_MARKER"}
        frame = self.client.get(frames[0])
        params = parse_qs(urlparse(frames[0]).query)
        lat, lon = params.get("lat", [None])[0], params.get("lng", [None])[0]
        # The embedded map must explicitly put the supplied variables into a marker.
        marker_verified = bool(re.search(r"markerPosition\s*=\s*new kakao\.maps\.LatLng\(geoLatitude,\s*geoLongitude\)", frame["payload"]))
        declared_lat = re.search(r'var geoLatitude\s*=\s*"([\d.]+)"', frame["payload"])
        declared_lon = re.search(r'var geoLongitude\s*=\s*"([\d.]+)"', frame["payload"])
        if not marker_verified or not declared_lat or not declared_lon or (lat, lon) != (declared_lat.group(1), declared_lon.group(1)):
            return None, {"reason": "NO_UNAMBIGUOUS_OFFICIAL_MARKER"}
        text = soup.get_text(" ", strip=True)
        address = re.search(r"주소\.\s*(.*?)\s*전화\.", text)
        identity = institution["canonical_name"] == "소망교도소" and "소망교도소" in (soup.title.get_text() if soup.title else "")
        return {"latitude": lat, "longitude": lon, "returned_address": address.group(1) if address else "",
                "source_url": directions, "provider": "official_institution_embedded_map_marker", "official": True,
                "institution_identity_verified": identity, "precision": "institution_marker_or_full_road_address",
                "evidence": "official_iframe_parameters_confirmed_as_marker", "embedded_map_url": frames[0],
                "embedded_map_sha256": frame["payload_sha256"], "query": normalized_address(institution["address"])}, {
                    "home_url": home["source_url"], "directions_url": directions,
                    "page_sha256": page["payload_sha256"], "retrieved_at": page["retrieved_at"]}


class KakaoAddressGeocoder:
    """Optional one-time fallback; caller explicitly chooses to enable it."""
    provider = "kakao_address_geocoder"
    endpoint = "https://dapi.kakao.com/v2/local/search/address.json"

    def __init__(self, client, key=None):
        self.client = client
        self.key = key or os.environ.get("KAKAO_REST_API_KEY")

    @staticmethod
    def parse_response(payload, query):
        result = []
        for item in payload.get("documents", []):
            road = item.get("road_address") or {}
            result.append({"latitude": item.get("y"), "longitude": item.get("x"),
                           "returned_address": road.get("address_name") or item.get("address_name"),
                           "provider": KakaoAddressGeocoder.provider, "official": False,
                           "source_url": KakaoAddressGeocoder.endpoint, "query": query,
                           "precision": "institution_marker_or_full_road_address" if item.get("address_type") == "ROAD_ADDR" and road else "coarse"})
        return result

    def locate(self, institution):
        if not self.key:
            return [], {"reason": "GEOCODER_KEY_NOT_CONFIGURED"}
        query = normalized_address(institution["address"])
        response = self.client.get(self.endpoint, params={"query": query},
                                   headers={"Authorization": f"KakaoAK {self.key}"}, json_response=True)
        return self.parse_response(response["payload"], query), {"queried_at": response["retrieved_at"], "query": query}
