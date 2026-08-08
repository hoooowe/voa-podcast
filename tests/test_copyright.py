"""Tests for copyright checking."""

from __future__ import annotations

from datetime import datetime

from voa_podcast.copyright_checker import CopyrightChecker
from voa_podcast.models import CopyrightStatus, VOAArticle


def _article(text: str, copyright_source: str | None = None, author: str | None = None):
    return VOAArticle(
        title="T",
        source_url="https://learningenglish.voanews.com/a/x/1.html",
        published_at=datetime(2026, 8, 8),
        english_text=text,
        audio_url="https://learningenglish.voanews.com/a.mp3",
        copyright_source=copyright_source,
        author=author,
    )


def test_voa_original():
    article = _article("This is a VOA original article about science.", copyright_source="VOA")
    result = CopyrightChecker().check(article)
    assert result.status == CopyrightStatus.VOA_ORIGINAL


def test_third_party_reuters():
    article = _article("This story is from Reuters about markets.")
    result = CopyrightChecker().check(article)
    assert result.status == CopyrightStatus.THIRD_PARTY
    assert result.matched_source == "Reuters"


def test_third_party_ap():
    article = _article("The report was prepared by the Associated Press.", author="AP")
    result = CopyrightChecker().check(article)
    assert result.status == CopyrightStatus.THIRD_PARTY


def test_original_when_no_markers_present():
    # Valid body, no third-party markers, no explicit source -> VOA original.
    article = _article("This is a clean VOA article body about science.", copyright_source=None)
    result = CopyrightChecker().check(article)
    assert result.status == CopyrightStatus.VOA_ORIGINAL


def test_unknown_when_empty_body():
    # No body to reason about -> unknown.
    article = _article("", copyright_source=None, author=None)
    result = CopyrightChecker().check(article)
    assert result.status == CopyrightStatus.UNKNOWN
