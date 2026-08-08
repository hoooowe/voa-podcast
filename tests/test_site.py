"""Tests for static HTML site generation."""

from __future__ import annotations

from voa_podcast.site_generator import SiteGenerator


def test_index_html_generated(tmp_config, sample_episode):
    SiteGenerator(tmp_config).generate([sample_episode])
    index = (tmp_config.docs_dir / "index.html").read_text(encoding="utf-8")
    assert "Daily English Listening" in index
    assert "AI Is Changing Education" in index
    assert "Subscribe with Apple Podcasts" in index
    assert "feed.xml" in index


def test_episode_html_generated(tmp_config, sample_episode):
    SiteGenerator(tmp_config).generate([sample_episode])
    page = (tmp_config.docs_dir / "episodes" / "ai-is-changing-education.html").read_text(
        encoding="utf-8"
    )
    assert "AI Is Changing Education" in page
    assert "Artificial intelligence is changing education." in page
    assert "人工智能正在改变教育。" in page
    assert sample_episode.source_url in page
    assert "VOA Original Audio" in page
    assert "001-ai-is-changing-education.mp3" in page


def test_index_lists_episodes_newest_first(tmp_config):
    from datetime import datetime, timezone

    from voa_podcast.models import Episode

    older = Episode(
        id=1, guid="voa-podcast-001", title="Older Episode", slug="older-episode",
        source="VOA Learning English",
        source_url="https://learningenglish.voanews.com/a/1.html",
        published_at=None, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        category="Science", english_text="a", chinese_text="b",
        audio_file="audio/001-x.mp3", audio_size=10, audio_type="audio/mpeg",
        copyright_status="VOA_ORIGINAL",
    )
    newer = Episode(
        id=2, guid="voa-podcast-002", title="Newer Episode", slug="newer-episode",
        source="VOA Learning English",
        source_url="https://learningenglish.voanews.com/a/2.html",
        published_at=None, created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        category="Science", english_text="a", chinese_text="b",
        audio_file="audio/002-x.mp3", audio_size=10, audio_type="audio/mpeg",
        copyright_status="VOA_ORIGINAL",
    )
    SiteGenerator(tmp_config).generate([older, newer])
    index = (tmp_config.docs_dir / "index.html").read_text(encoding="utf-8")
    assert index.index("Newer Episode") < index.index("Older Episode")


def test_empty_index(tmp_config):
    SiteGenerator(tmp_config).generate([])
    index = (tmp_config.docs_dir / "index.html").read_text(encoding="utf-8")
    assert "No episodes yet" in index
