"""Tests for episode repository: dedup, GUID stability, slug generation."""

from __future__ import annotations

from datetime import datetime, timezone

from voa_podcast.episode_repository import (
    EpisodeRepository,
    audio_filename,
    make_slug,
)
from voa_podcast.models import Episode


def _make_episode(repo: EpisodeRepository, title: str, url: str) -> Episode:
    return repo.create_episode(
        title=title,
        slug=make_slug(title),
        source_url=url,
        published_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        category="Science",
        english_text="Some english text.",
        chinese_text="一些中文。",
        audio_file="audio/x.mp3",
        audio_size=100,
        audio_type="audio/mpeg",
        audio_sha256="sha-" + title,
        copyright_status="VOA_ORIGINAL",
    )


def test_duplicate_detection_by_url(tmp_config):
    repo = EpisodeRepository(tmp_config.episodes_file)
    _make_episode(repo, "First", "https://learningenglish.voanews.com/a/1.html")
    assert repo.find_by_url("https://learningenglish.voanews.com/a/1.html") is not None
    assert repo.find_by_url("https://learningenglish.voanews.com/a/2.html") is None


def test_duplicate_detection_by_audio_sha256(tmp_config):
    repo = EpisodeRepository(tmp_config.episodes_file)
    _make_episode(repo, "First", "https://learningenglish.voanews.com/a/1.html")
    found = repo.find_by_audio_sha256("sha-First")
    assert found is not None
    assert found.title == "First"


def test_guid_stable_after_resave(tmp_config):
    repo = EpisodeRepository(tmp_config.episodes_file)
    ep = _make_episode(repo, "Stable", "https://learningenglish.voanews.com/a/s.html")
    original_guid = ep.guid
    original_id = ep.id

    # Reload and re-save (simulating rebuild) — GUID must not change.
    episodes = repo.load_all()
    repo.save_all(episodes)
    reloaded = repo.load_all()[0]
    assert reloaded.guid == original_guid
    assert reloaded.id == original_id


def test_guid_format(tmp_config):
    repo = EpisodeRepository(tmp_config.episodes_file)
    ep = _make_episode(repo, "First", "https://learningenglish.voanews.com/a/1.html")
    assert ep.guid == "voa-podcast-001"
    ep2 = _make_episode(repo, "Second", "https://learningenglish.voanews.com/a/2.html")
    assert ep2.guid == "voa-podcast-002"


def test_next_id_increments(tmp_config):
    repo = EpisodeRepository(tmp_config.episodes_file)
    assert repo.next_id() == 1
    _make_episode(repo, "First", "https://learningenglish.voanews.com/a/1.html")
    assert repo.next_id() == 2


def test_slug_generation():
    assert make_slug("AI Is Changing Education!") == "ai-is-changing-education"
    assert make_slug("Hello, World: A Test") == "hello-world-a-test"


def test_audio_filename_format():
    assert audio_filename(1, "ai-edu") == "001-ai-edu.mp3"
    assert audio_filename(12, "test") == "012-test.mp3"


def test_unique_slug_on_collision(tmp_config):
    repo = EpisodeRepository(tmp_config.episodes_file)
    ep1 = _make_episode(repo, "Same Title", "https://learningenglish.voanews.com/a/1.html")
    ep2 = _make_episode(repo, "Same Title", "https://learningenglish.voanews.com/a/2.html")
    assert ep1.slug == "same-title"
    assert ep2.slug == "same-title-2"
