from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class PoliteHttpClient:
    def __init__(self, *, user_agent: str, timeout: float, delay: float, retries: int) -> None:
        self.timeout = timeout
        self.delay = delay
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            # The site's list/detail POSTs are read-only form submissions.
            allowed_methods=frozenset({"GET", "HEAD", "POST"}),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=1))
        self.session.mount("http://", HTTPAdapter(max_retries=retry, pool_maxsize=1))

    def get(self, url: str, *, stream: bool = False) -> requests.Response:
        return self._request("GET", url, stream=stream)

    def post(self, url: str, *, data: dict[str, str]) -> requests.Response:
        return self._request("POST", url, data=data)

    def _request(self, method: str, url: str, **kwargs: object) -> requests.Response:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            self._last_request = time.monotonic()
            response.raise_for_status()
            return response
        except requests.RequestException:
            logging.exception("Request failed: %s", url)
            raise

