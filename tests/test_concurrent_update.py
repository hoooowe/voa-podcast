"""Concurrent episode updates must not publish a stale snapshot."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Event

import pytest
from filelock import Timeout

from voa_podcast.episode_repository import EpisodeRepository
from voa_podcast.episode_update import publish_episode_update
from voa_podcast.rss_generator import RSSGenerator


def test_overlapping_updates_publish_consistent_audio(tmp_config, sample_episode, monkeypatch):
    repo = EpisodeRepository(tmp_config.episodes_file)
    other = replace(
        sample_episode, id=2, guid="voa-podcast-002", slug="another-episode",
        audio_file="audio/002-another-episode.mp3", source_url="https://example.org/2",
    )
    for episode in (sample_episode, other):
        audio = f"original audio {episode.id}".encode()
        episode.audio_sha256 = hashlib.sha256(audio).hexdigest()
        episode.audio_size = len(audio)
        (tmp_config.docs_dir / episode.audio_file).write_bytes(audio)
        repo.add(episode)

    both_rendered = Barrier(2, timeout=10)
    generate = RSSGenerator.generate

    def render_from_same_snapshot(generator, episodes):
        result = generate(generator, episodes)
        both_rendered.wait()
        return result

    monkeypatch.setattr(RSSGenerator, "generate", render_from_same_snapshot)
    committing = Event()
    finish_commit = Event()
    replace_file = Path.replace

    def pause_at_record_commit(path, target):
        if target == tmp_config.episodes_file:
            committing.set()
            assert finish_commit.wait(timeout=10)
        return replace_file(path, target)

    monkeypatch.setattr(Path, "replace", pause_at_record_commit)

    def update(episode):
        audio = f"new audio {episode.id}".encode()
        download = tmp_config.project_root / f"new-{episode.id}.mp3"
        download.write_bytes(audio)
        updated = replace(
            episode, title=f"Updated {episode.id}", audio_size=len(audio),
            audio_sha256=hashlib.sha256(audio).hexdigest(),
        )
        try:
            publish_episode_update(tmp_config, episode, updated, download)
        except RuntimeError as exc:
            assert "Episode data changed" in str(exc)
            return episode
        return updated

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(update, episode) for episode in (sample_episode, other)]
        try:
            assert committing.wait(timeout=10)
            with pytest.raises(Timeout), repo.publication_lock().acquire(timeout=0):
                pass
        finally:
            finish_commit.set()
        expected = [result.result() for result in results]

    assert sum(ep.title.startswith("Updated ") for ep in expected) == 1
    assert repo.load_all() == expected
    for ep in expected:
        audio = (tmp_config.docs_dir / ep.audio_file).read_bytes()
        assert hashlib.sha256(audio).hexdigest() == ep.audio_sha256
