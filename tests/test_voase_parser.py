"""Tests for the voase.cn parser (CN-accessible VOA mirror)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

from voa_podcast.content_parser import VOASEContentParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VOASE_URL = (
    "https://www.voase.cn/2025/03/2025-03-18-%5BHealth-and-Lifestyle%5D-"
    "Wilbur-and-Orville-Wright_-The-First-Airplane.html"
)


def _load_soup() -> BeautifulSoup:
    html = (FIXTURES_DIR / "voase_article.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "html.parser")


def _load_txt() -> str:
    return (FIXTURES_DIR / "voase_article.txt").read_text(encoding="utf-8")


def test_voase_title():
    article = VOASEContentParser().parse(VOASE_URL, _load_soup(), txt_text=_load_txt())
    assert article.title == "Wilbur and Orville Wright: The First Airplane"


def test_voase_date():
    article = VOASEContentParser().parse(VOASE_URL, _load_soup(), txt_text=_load_txt())
    assert article.published_at == datetime(2025, 3, 18)


def test_voase_category():
    article = VOASEContentParser().parse(VOASE_URL, _load_soup(), txt_text=_load_txt())
    assert article.category == "Health and Lifestyle"


def test_voase_audio_url_encoded():
    article = VOASEContentParser().parse(VOASE_URL, _load_soup(), txt_text=_load_txt())
    # Spaces and brackets must be percent-encoded.
    assert "%20" in article.audio_url
    assert " " not in article.audio_url
    assert article.audio_url.endswith(".mp3")
    assert article.audio_url.startswith("https://www.voase.cn/2025/03/")


def test_voase_body_from_txt_preserves_paragraphs():
    article = VOASEContentParser().parse(VOASE_URL, _load_soup(), txt_text=_load_txt())
    paragraphs = [p for p in article.english_text.split("\n\n") if p]
    assert len(paragraphs) == 3
    assert paragraphs[0].startswith("Wilbur and Orville Wright are the American inventors")
    # Title/date header must not leak into the body.
    assert "2025-03-18" not in article.english_text


def test_voase_body_fallback_to_li_when_no_txt():
    article = VOASEContentParser().parse(VOASE_URL, _load_soup(), txt_text=None)
    sentences = [p for p in article.english_text.split("\n\n") if p]
    assert len(sentences) == 5
    assert sentences[0].startswith("Wilbur and Orville Wright are the American inventors")


def test_voase_extract_txt_url():
    url = VOASEContentParser().extract_txt_url(VOASE_URL, _load_soup())
    assert url is not None
    assert url.endswith(".txt")
    assert "%20" in url


def test_voase_copyright_source_is_voa():
    article = VOASEContentParser().parse(VOASE_URL, _load_soup(), txt_text=_load_txt())
    assert article.copyright_source == "VOA"


def test_voase_fetcher_validates_voase_url():
    from voa_podcast.voa_fetcher import VOAContentFetcher

    # Should not raise.
    VOAContentFetcher.validate_url(VOASE_URL)
    VOAContentFetcher.validate_url("https://voase.cn/2025/03/some-article.html")


def test_voase_fetcher_rejects_unsupported_host():
    import pytest

    from voa_podcast.voa_fetcher import VOAContentFetcher, VOAFetchError

    with pytest.raises(VOAFetchError):
        VOAContentFetcher.validate_url("https://example.com/article.html")
