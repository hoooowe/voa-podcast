"""Fetches VOA Learning English article HTML pages."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .models import VOAArticle
from .content_parser import VOAContentParser

logger = logging.getLogger(__name__)

VOA_HOST = "learningenglish.voanews.com"
DEFAULT_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class VOAFetchError(Exception):
    """Raised when a VOA page cannot be fetched or is invalid."""


class VOAContentFetcher:
    """Downloads a VOA Learning English page and parses it into a VOAArticle."""

    def __init__(self, parser: VOAContentParser | None = None) -> None:
        self._parser = parser or VOAContentParser()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    @staticmethod
    def validate_url(url: str) -> None:
        """Ensure the URL points to VOA Learning English."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise VOAFetchError(f"Invalid URL scheme: {parsed.scheme}")
        if parsed.netloc != VOA_HOST:
            raise VOAFetchError(
                f"URL must be from {VOA_HOST}, got: {parsed.netloc}"
            )

    def fetch_html(self, url: str) -> str:
        """Download the raw HTML for a VOA URL."""
        logger.info("[FETCH] Downloading VOA article...")
        try:
            resp = self._session.get(url, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            raise VOAFetchError(f"Failed to fetch VOA page: {exc}") from exc
        if resp.status_code != 200:
            raise VOAFetchError(
                f"VOA page returned HTTP {resp.status_code} for {url}"
            )
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def fetch(self, url: str) -> VOAArticle:
        """Validate, download, and parse a VOA article URL."""
        self.validate_url(url)
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")
        return self._parser.parse(url, soup)
