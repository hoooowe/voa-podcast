"""Tests for VOA HTML parsing (multi-strategy, offline)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from voa_podcast.content_parser import VOAContentParser, VOAParseError
from voa_podcast.models import VOAArticle

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _parse_fixture() -> VOAArticle:
    html = (FIXTURES_DIR / "voa_article.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    return VOAContentParser().parse(
        "https://learningenglish.voanews.com/a/ai-education/123.html", soup
    )


def test_parse_title():
    article = _parse_fixture()
    assert article.title == "AI Is Changing Education"


def test_parse_published_at():
    article = _parse_fixture()
    assert article.published_at == datetime(2026, 8, 8, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_category():
    article = _parse_fixture()
    assert article.category == "Science"


def test_parse_audio_url():
    article = _parse_fixture()
    assert article.audio_url == "https://learningenglish.voanews.com/audio/ai-education.mp3"


def test_parse_body_preserves_paragraphs():
    article = _parse_fixture()
    paragraphs = [p for p in article.english_text.split("\n\n") if p]
    assert len(paragraphs) == 3
    assert paragraphs[0] == "Artificial intelligence is changing education."


def test_parse_body_strips_noise():
    article = _parse_fixture()
    assert "Related Stories" not in article.english_text
    assert "Share" not in article.english_text
    assert "VOA Learning English" not in article.english_text  # nav header


def test_parse_source_url():
    article = _parse_fixture()
    assert article.source_url.startswith("https://learningenglish.voanews.com/")


def test_parse_copyright_source_voa():
    from voa_podcast.copyright_checker import CopyrightChecker
    from voa_podcast.models import CopyrightStatus

    article = _parse_fixture()
    # The parser may not find an explicit copyright holder (footer is stripped),
    # but the copyright checker must still classify clean VOA content as original.
    result = CopyrightChecker().check(article)
    assert result.status == CopyrightStatus.VOA_ORIGINAL


def test_parse_raises_when_no_content():
    soup = BeautifulSoup("<html><body><p>x</p></body></html>", "html.parser")
    with pytest.raises(VOAParseError):
        VOAContentParser().parse(
            "https://learningenglish.voanews.com/a/x/1.html", soup
        )


def test_parse_audio_fallback_to_anchor():
    html = """
    <html><head>
    <script type="application/ld+json">{"@type":"NewsArticle","headline":"T","articleBody":"Hello world this is a test article body."}</script>
    </head><body>
    <h1>T</h1>
    <div class="article-content"><p>Hello world this is a test article body.</p></div>
    <a href="/media/song.mp3">Download audio</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    article = VOAContentParser().parse(
        "https://learningenglish.voanews.com/a/x/2.html", soup
    )
    assert article.audio_url == "https://learningenglish.voanews.com/media/song.mp3"
