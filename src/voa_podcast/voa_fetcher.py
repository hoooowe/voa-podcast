"""Fetches VOA Learning English article HTML pages.

Supports two sources:
    - learningenglish.voanews.com  (official VOA, multi-strategy parser)
    - www.voase.cn / voase.cn       (CN-accessible mirror; downloads .txt
                                     for clean paragraph text + .mp3 audio)
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .content_parser import VOAContentParser, VOASEContentParser
from .models import VOAArticle

logger = logging.getLogger(__name__)

VOA_HOST = "learningenglish.voanews.com"
VOASE_HOSTS = ("www.voase.cn", "voase.cn")
ALLOWED_HOSTS = (VOA_HOST, *VOASE_HOSTS)
DEFAULT_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class VOAFetchError(Exception):
    """Raised when a VOA page cannot be fetched or is invalid."""


class VOAContentFetcher:
    """Downloads a VOA article page and parses it into a VOAArticle."""

    def __init__(self, parser: VOAContentParser | None = None) -> None:
        self._parser = parser or VOAContentParser()
        self._voase_parser = VOASEContentParser()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    @staticmethod
    def validate_url(url: str) -> None:
        """Ensure the URL points to a supported VOA source."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise VOAFetchError(f"Invalid URL scheme: {parsed.scheme}")
        if parsed.netloc not in ALLOWED_HOSTS:
            raise VOAFetchError(
                f"URL must be from {VOA_HOST} or voase.cn, got: {parsed.netloc}"
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

    def fetch_text(self, url: str) -> str:
        """Download a plain-text file (e.g. voase.cn .txt transcript)."""
        try:
            resp = self._session.get(url, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            raise VOAFetchError(f"Failed to fetch text file: {exc}") from exc
        if resp.status_code != 200:
            raise VOAFetchError(f"Text file returned HTTP {resp.status_code}")
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def fetch(self, url: str) -> VOAArticle:
        """Validate, download, and parse a VOA article URL."""
        self.validate_url(url)
        host = urlparse(url).netloc
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")

        if host in VOASE_HOSTS:
            return self._fetch_voase(url, soup)
        return self._parser.parse(url, soup)

    def _fetch_voase(self, url: str, soup: BeautifulSoup) -> VOAArticle:
        """Parse a voase.cn article, downloading its .txt transcript if available."""
        txt_text: str | None = None
        txt_url = self._voase_parser.extract_txt_url(url, soup)
        if txt_url:
            try:
                txt_text = self.fetch_text(txt_url)
                logger.info("[FETCH] Transcript .txt downloaded.")
            except VOAFetchError as exc:
                logger.warning("[FETCH] Could not download .txt transcript: %s", exc)
                txt_text = None
        return self._voase_parser.parse(url, soup, txt_text=txt_text)
