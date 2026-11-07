"""A small polite HTTP client, because every data source here is a free public service.

Retries cover the ordinary blips of long runs, the rate limiter keeps us well under each
service's limit, and the identifying User-Agent is the generic project name: no email or
personal detail ever goes in a request.
"""

import threading
import time

import httpx

from .config import USER_AGENT


class Client:
    """httpx wrapper with a minimum gap between requests and exponential-backoff retries."""

    def __init__(self, min_interval: float = 0.25, retries: int = 6, timeout: float = 60.0):
        self.min_interval = min_interval
        self.retries = retries
        self._last = 0.0
        self._lock = threading.Lock()
        self._http = httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True
        )

    def _wait_turn(self) -> None:
        with self._lock:
            gap = self.min_interval - (time.monotonic() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()

    def get(self, url: str, **kwargs) -> httpx.Response | None:
        """Return the response, or None on a 404/410. Raise after repeated failures."""
        for attempt in range(self.retries):
            self._wait_turn()
            try:
                r = self._http.get(url, **kwargs)
            except httpx.HTTPError:
                time.sleep(min(2**attempt, 60))
                continue
            if r.status_code in (404, 410):
                return None
            if r.status_code == 429 or r.status_code >= 500:
                wait = r.headers.get("retry-after", "")
                time.sleep(float(wait) if wait.isdigit() else min(2**attempt, 60))
                continue
            r.raise_for_status()
            return r
        raise RuntimeError(f"gave up after {self.retries} tries: {url.split('?')[0]}")
