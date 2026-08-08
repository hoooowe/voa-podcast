"""Multi-strategy parser for VOA Learning English article pages.

Parsing priority for each field:
    JSON-LD  ->  OpenGraph/meta  ->  HTML DOM  ->  fallback

Selectors are centralized in SELECTORS so page-structure changes only
require updating this module, not the rest of the pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, quote

from bs4 import BeautifulSoup, Tag

from .models import VOAArticle, Sentence

logger = logging.getLogger(__name__)

# Centralized CSS selectors (tried in order, first match wins).
BODY_SELECTORS = [
    "div.article-content",
    "div#article-content",
    "div.article__content",
    "div.content",
    "div.body",
    "div.article-body",
    "article",
    "div[itemprop='articleBody']",
]

TITLE_SELECTORS = [
    "h1.article-title",
    "h1#article-title",
    "h1.title",
    "h1",
    "meta[property='og:title']",
]

CATEGORY_SELECTORS = [
    "span.category",
    "div.category",
    "meta[property='article:section']",
]

AUTHOR_SELECTORS = [
    "span.author",
    "div.author",
    "meta[name='author']",
    "meta[property='article:author']",
]

DATE_SELECTORS = [
    "time[datetime]",
    "span.date",
    "div.date",
    "meta[property='article:published_time']",
]

# Elements / text patterns to strip from the article body.
NOISE_SELECTORS = [
    "nav", "footer", "header", "aside",
    ".related", ".related-stories", ".share", ".sharing",
    ".subscribe", ".newsletter", ".ad", ".ads", ".advertisement",
    ".author-bio", ".bio", ".tags", ".tag-list",
    ".button", ".btn", ".social", ".comments",
    "script", "style", "iframe", "form",
]

THIRD_PARTY_PATTERNS = [
    r"\bAssociated Press\b",
    r"\bAP\b",
    r"\bReuters\b",
    r"\bAFP\b",
    r"\bAgence France-Presse\b",
]

# Text snippets considered as non-article noise.
NOISE_TEXT_PATTERNS = [
    re.compile(r"^Related Stories$", re.I),
    re.compile(r"^Subscribe$", re.I),
    re.compile(r"^Share$", re.I),
    re.compile(r"^Read More$", re.I),
    re.compile(r"^Comments$", re.I),
]


class VOAParseError(Exception):
    """Raised when article content cannot be extracted."""


class VOAContentParser:
    """Parses a BeautifulSoup document into a VOAArticle using fallbacks."""

    def parse(self, url: str, soup: BeautifulSoup) -> VOAArticle:
        """Parse a VOA page into a VOAArticle, raising VOAParseError on failure."""
        jsonld = self._extract_jsonld(soup)

        title = self._extract_title(soup, jsonld)
        published_at = self._extract_date(soup, jsonld)
        english_text = self._extract_body(soup, jsonld)
        audio_url = self._extract_audio(soup, jsonld, url)
        category = self._extract_category(soup, jsonld)
        author = self._extract_author(soup, jsonld)
        copyright_source = self._extract_copyright_source(soup, jsonld, english_text)

        logger.info("[PARSE] Title found.")
        logger.info("[PARSE] Audio found.")

        return VOAArticle(
            title=title,
            source_url=url,
            published_at=published_at,
            english_text=english_text,
            audio_url=audio_url,
            category=category,
            author=author,
            copyright_source=copyright_source,
        )

    # ------------------------------------------------------------------ #
    # JSON-LD helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_jsonld(soup: BeautifulSoup) -> dict:
        """Collect the first usable JSON-LD object (NewsArticle / Article)."""
        for tag in soup.find_all("script", type="application/ld+json"):
            raw = tag.string or tag.get_text() or ""
            raw = raw.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            for item in _as_list(data):
                if isinstance(item, dict) and item.get("@type") in (
                    "NewsArticle",
                    "Article",
                    "Report",
                ):
                    return item
        return {}

    # ------------------------------------------------------------------ #
    # Field extractors
    # ------------------------------------------------------------------ #
    def _extract_title(self, soup: BeautifulSoup, jsonld: dict) -> str:
        if jsonld.get("headline"):
            return _clean_text(jsonld["headline"])
        for selector in TITLE_SELECTORS:
            tag = soup.select_one(selector)
            if tag:
                if tag.name == "meta":
                    text = tag.get("content", "")
                else:
                    text = tag.get_text()
                text = _clean_text(text)
                if text:
                    return text
        raise VOAParseError("Unable to extract VOA article title.")

    def _extract_date(self, soup: BeautifulSoup, jsonld: dict) -> datetime | None:
        raw = (
            jsonld.get("datePublished")
            or jsonld.get("dateCreated")
            or self._meta_content(soup, "property", "article:published_time")
        )
        if not raw:
            for selector in DATE_SELECTORS:
                tag = soup.select_one(selector)
                if not tag:
                    continue
                raw = tag.get("datetime") or tag.get_text()
                if raw:
                    break
        if not raw:
            return None
        return _parse_datetime(_clean_text(raw))

    def _extract_body(self, soup: BeautifulSoup, jsonld: dict) -> str:
        body_text = jsonld.get("articleBody") or jsonld.get("description")
        if body_text and len(_clean_text(body_text)) > 50:
            return _clean_paragraphs(body_text)

        for selector in BODY_SELECTORS:
            container = soup.select_one(selector)
            if not container:
                continue
            paragraphs = self._extract_paragraphs(container)
            if paragraphs:
                return "\n\n".join(paragraphs)

        # Fallback: scan all <p> inside main content areas.
        paragraphs = self._extract_paragraphs(soup)
        if paragraphs:
            return "\n\n".join(paragraphs)

        raise VOAParseError("Unable to extract VOA article text.")

    def _extract_paragraphs(self, container: Tag) -> list[str]:
        """Extract cleaned paragraph text from a container, removing noise."""
        clone = BeautifulSoup(str(container), "html.parser")
        for sel in NOISE_SELECTORS:
            for node in clone.select(sel):
                node.decompose()

        paragraphs: list[str] = []
        for p in clone.find_all(["p", "h2", "h3"]):
            text = _clean_text(p.get_text())
            if not text:
                continue
            if any(pat.match(text) for pat in NOISE_TEXT_PATTERNS):
                continue
            if len(text) < 2:
                continue
            paragraphs.append(text)
        return paragraphs

    def _extract_audio(self, soup: BeautifulSoup, jsonld: dict, base_url: str) -> str:
        # 1. JSON-LD associated media / contentUrl.
        for key in ("associatedMedia", "audio", "video"):
            media = jsonld.get(key)
            if isinstance(media, dict):
                url = media.get("contentUrl") or media.get("url")
                if url:
                    return urljoin(base_url, url)
            if isinstance(media, list):
                for item in media:
                    if isinstance(item, dict):
                        url = item.get("contentUrl") or item.get("url")
                        if url:
                            return urljoin(base_url, url)

        # 2. <audio> / <source> tags.
        for tag in soup.find_all(["audio", "source"]):
            src = tag.get("src")
            if src and ".mp3" in src.lower():
                return urljoin(base_url, src)

        # 3. <a> links to mp3.
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".mp3" in href.lower():
                return urljoin(base_url, href)

        # 4. data-url / data-audio attributes.
        for tag in soup.find_all(attrs={"data-url": True}):
            val = tag["data-url"]
            if ".mp3" in val.lower():
                return urljoin(base_url, val)
        for tag in soup.find_all(attrs={"data-audio": True}):
            val = tag["data-audio"]
            if ".mp3" in val.lower() or val.startswith("http"):
                return urljoin(base_url, val)

        raise VOAParseError("Unable to locate VOA audio file.")

    def _extract_category(self, soup: BeautifulSoup, jsonld: dict) -> str | None:
        if jsonld.get("articleSection"):
            return _clean_text(jsonld["articleSection"])
        for selector in CATEGORY_SELECTORS:
            tag = soup.select_one(selector)
            if tag:
                text = tag.get("content") or tag.get_text()
                text = _clean_text(text)
                if text:
                    return text
        return None

    def _extract_author(self, soup: BeautifulSoup, jsonld: dict) -> str | None:
        author = jsonld.get("author")
        if isinstance(author, dict) and author.get("name"):
            return _clean_text(author["name"])
        if isinstance(author, str) and author:
            return _clean_text(author)
        for selector in AUTHOR_SELECTORS:
            tag = soup.select_one(selector)
            if tag:
                text = tag.get("content") or tag.get_text()
                text = _clean_text(text)
                if text:
                    return text
        return None

    def _extract_copyright_source(
        self, soup: BeautifulSoup, jsonld: dict, body_text: str
    ) -> str | None:
        copyright_text = jsonld.get("copyrightHolder") or jsonld.get("copyrightNotice")
        if isinstance(copyright_text, dict):
            copyright_text = copyright_text.get("name")
        if copyright_text:
            return _clean_text(str(copyright_text))
        meta = self._meta_content(soup, "name", "copyright")
        if meta:
            return _clean_text(meta)
        # Scan body for third-party markers.
        for pattern in THIRD_PARTY_PATTERNS:
            match = re.search(pattern, body_text)
            if match:
                return match.group(0)
        return None

    @staticmethod
    def _meta_content(soup: BeautifulSoup, attr: str, value: str) -> str | None:
        tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            return tag["content"]
        return None


# ---------------------------------------------------------------------- #
# Module-level helpers
# ---------------------------------------------------------------------- #
def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    return [value]


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _clean_paragraphs(text: str) -> str:
    parts = [_clean_text(p) for p in text.split("\n")]
    parts = [p for p in parts if p]
    return "\n\n".join(parts)


def _parse_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------- #
# voase.cn parser (CN-accessible mirror of VOA Special English)
# ---------------------------------------------------------------------- #
class VOASEContentParser:
    """Parser for voase.cn article pages.

    voase.cn stores each article as an HTML page (with <h2> title, <h3> date,
    sentence-level <li> body, and download links for .txt/.lrc/.mp3) plus a
    downloadable .txt file containing clean paragraph text. We prefer the
    .txt for the body (real paragraphs) and fall back to <li> sentences.
    """

    def parse(
        self,
        url: str,
        soup: BeautifulSoup,
        txt_text: str | None = None,
        lrc_text: str | None = None,
    ) -> VOAArticle:
        title = self._extract_title(soup)
        date_str, published_at = self._extract_date(soup)
        category = self._extract_category(soup, title)
        audio_url = self._extract_audio(url, soup)

        sentences: list[Sentence] | None = None
        english_text = ""

        # Prefer .lrc: it gives per-sentence audio timestamps (click-to-seek).
        if lrc_text:
            timed = parse_lrc(lrc_text)
            if timed:
                sentences = [Sentence(start=start, en=text) for start, text in timed]
                english_text = "\n\n".join(s.en for s in sentences)

        # Fall back to .txt (clean paragraphs, no timestamps).
        if not english_text and txt_text:
            english_text = self._parse_txt_body(txt_text, title, date_str)

        # Last resort: <li> sentences.
        if not english_text:
            english_text = self._extract_body_from_li(soup)

        if not english_text:
            raise VOAParseError("Unable to extract VOA article text.")

        logger.info("[PARSE] Title found.")
        logger.info("[PARSE] Audio found.")
        if sentences:
            logger.info("[PARSE] %d timestamped sentences from .lrc.", len(sentences))

        return VOAArticle(
            title=title,
            source_url=url,
            published_at=published_at,
            english_text=english_text,
            audio_url=audio_url,
            category=category,
            author="VOA Special English",
            copyright_source="VOA",
            sentences=sentences,
        )

    def extract_txt_url(self, base_url: str, soup: BeautifulSoup) -> str | None:
        """Return the absolute .txt download URL, if present."""
        a = soup.find("a", id="btndl-txt")
        if not a or not a.get("href"):
            return None
        return _join_url(base_url, a["href"])

    def extract_lrc_url(self, base_url: str, soup: BeautifulSoup) -> str | None:
        """Return the absolute .lrc download URL, if present."""
        a = soup.find("a", id="btndl-lrc")
        if not a or not a.get("href"):
            return None
        return _join_url(base_url, a["href"])

    def _extract_title(self, soup: BeautifulSoup) -> str:
        h2 = soup.find("h2")
        if h2:
            text = _clean_text(h2.get_text())
            if text:
                return text
        tag = soup.find("title")
        if tag:
            # title looks like: "2025-03-18 [Category] Article Title"
            text = _clean_text(tag.get_text())
            text = re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", text)
            text = re.sub(r"^\[[^\]]*\]\s*", "", text)
            if text:
                return text
        raise VOAParseError("Unable to extract VOA article title.")

    def _extract_date(self, soup: BeautifulSoup) -> tuple[str | None, datetime | None]:
        h3 = soup.find("h3")
        raw = _clean_text(h3.get_text()) if h3 else None
        if not raw:
            tag = soup.find("title")
            if tag:
                m = re.search(r"(\d{4}-\d{2}-\d{2})", tag.get_text())
                raw = m.group(1) if m else None
        return raw, _parse_datetime(raw) if raw else None

    def _extract_category(self, soup: BeautifulSoup, title: str) -> str | None:
        # Category appears in brackets in the page <title>, e.g. [Health and Lifestyle].
        tag = soup.find("title")
        text = tag.get_text() if tag else title
        m = re.search(r"\[([^\]]+)\]", text)
        if m:
            return _clean_text(m.group(1))
        return None

    def _extract_audio(self, base_url: str, soup: BeautifulSoup) -> str:
        a = soup.find("a", id="btndl-mp3")
        if a and a.get("href"):
            return _join_url(base_url, a["href"])
        # Fallback: any .mp3 link on the page.
        for a_tag in soup.find_all("a", href=True):
            if ".mp3" in a_tag["href"].lower():
                return _join_url(base_url, a_tag["href"])
        raise VOAParseError("Unable to locate VOA audio file.")

    def _extract_body_from_li(self, soup: BeautifulSoup) -> str:
        sentences = [
            _clean_text(li.get_text())
            for li in soup.find_all("li")
            if _clean_text(li.get_text())
        ]
        return "\n\n".join(sentences) if sentences else ""

    @staticmethod
    def _parse_txt_body(txt: str, title: str, date_str: str | None) -> str:
        """Parse a voase.cn .txt file into clean paragraph text.

        The .txt starts with a title line and a date line, followed by blank
        lines and the article paragraphs (separated by blank lines).
        """
        lines = txt.splitlines()
        body_lines: list[str] = []
        skipping_header = True
        for line in lines:
            s = line.strip()
            if skipping_header:
                if (
                    s == ""
                    or s == title
                    or s == date_str
                    or re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)
                ):
                    continue
                skipping_header = False
            body_lines.append(line)
        text = "\n".join(body_lines).strip()
        if not text:
            return ""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        return "\n\n".join(paragraphs)


def _join_url(base_url: str, href: str) -> str:
    """Join a (possibly space/bracket-containing) relative href onto base_url.

    voase.cn download filenames contain spaces and brackets, so the href must
    be percent-encoded before joining.
    """
    return urljoin(base_url, quote(href, safe="/"))


# Matches a leading LRC timestamp like [00:17.72] or [01:03.76].
_LRC_TIME_RE = re.compile(r"\[(\d+):(\d{2}(?:\.\d+)?)\]")
# Metadata ID tags like [ti:...], [al:...], [ar:...], [by:...], [offset:...].
_LRC_META_RE = re.compile(r"^\s*\[[a-z]+:", re.IGNORECASE)


def parse_lrc(lrc_text: str) -> list[tuple[float, str]]:
    """Parse an LRC transcript into a list of ``(start_seconds, text)``.

    Skips metadata header lines (``[ti:...]``, ``[al:...]``, etc.) and any
    timestamped lines with no text.
    """
    sentences: list[tuple[float, str]] = []
    for line in lrc_text.splitlines():
        if _LRC_META_RE.match(line):
            continue
        m = _LRC_TIME_RE.match(line)
        if not m:
            continue
        minutes = int(m.group(1))
        seconds = float(m.group(2))
        start = minutes * 60 + seconds
        text = line[m.end():].strip()
        if text:
            sentences.append((start, text))
    return sentences
