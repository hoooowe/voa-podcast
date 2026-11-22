import hashlib
import sys
from pathlib import Path

import pytest

from voa_podcast.episode_repository import EpisodeRepository
from voa_podcast.models import AudioMetadata, VOAArticle


AUDIO = b"downloaded audio"
URL = "https://learningenglish.voanews.com/a/another-story/123.html"


@pytest.fixture
def pipeline(tmp_config, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import add_episode

    monkeypatch.setattr(add_episode, "load_config", lambda: tmp_config)

    def fetch(self, url):
        return VOAArticle("Another Story", url, None, "A story.", "https://example.com/audio.mp3")

    monkeypatch.setattr(add_episode.VOAContentFetcher, "fetch", fetch)

    def download(self, url, destination):
        destination.write_bytes(AUDIO)
        return AudioMetadata(destination, len(AUDIO), "audio/mpeg", hashlib.sha256(AUDIO).hexdigest())

    monkeypatch.setattr(add_episode.AudioDownloader, "download", download)
    return add_episode


@pytest.mark.parametrize("legacy_file", [False, True])
def test_duplicate_audio_preserves_existing_files(pipeline, tmp_config, sample_episode, legacy_file):
    repo = EpisodeRepository(tmp_config.episodes_file)
    sample_episode.audio_sha256 = hashlib.sha256(AUDIO).hexdigest()
    sample_episode.audio_size = len(AUDIO)
    repo.add(sample_episode)
    original = tmp_config.docs_dir / sample_episode.audio_file
    original.write_bytes(AUDIO)
    expected = {original.name: AUDIO}
    if legacy_file:
        prior_download = tmp_config.audio_dir / "002-another-story.mp3"
        prior_download.write_bytes(b"legacy file")
        expected[prior_download.name] = b"legacy file"

    assert pipeline.run_pipeline(URL) == 2
    assert {p.name: p.read_bytes() for p in tmp_config.audio_dir.iterdir()} == expected
    assert repo.load_all() == [sample_episode]


def test_distinct_audio_can_import_alongside_legacy_file(pipeline, tmp_config, monkeypatch):
    legacy = tmp_config.audio_dir / "001-another-story.mp3"
    legacy.write_bytes(b"legacy file")
    monkeypatch.setattr(pipeline.OpenAICompatibleTranslator, "translate", lambda self, text: "故事")

    assert pipeline.run_pipeline(URL) == 0
    episode, = EpisodeRepository(tmp_config.episodes_file).load_all()
    assert (tmp_config.docs_dir / episode.audio_file).read_bytes() == AUDIO
    assert legacy.read_bytes() == b"legacy file"
    assert episode.audio_file in (tmp_config.docs_dir / "feed.xml").read_text(encoding="utf-8")


def test_interrupted_download_leaves_no_partial_audio(pipeline, tmp_config, monkeypatch):
    def interrupt(self, url, destination):
        destination.write_bytes(b"partial")
        raise OSError("interrupted")

    monkeypatch.setattr(pipeline.AudioDownloader, "download", interrupt)
    with pytest.raises(OSError, match="interrupted"):
        pipeline.run_pipeline(URL)
    assert list(tmp_config.audio_dir.iterdir()) == []
    assert EpisodeRepository(tmp_config.episodes_file).load_all() == []


@pytest.mark.parametrize("first_download_fails", [False, True])
def test_feed_batch_reuses_only_confirmed_duplicates(
    pipeline, tmp_config, sample_episode, monkeypatch, first_download_fails
):
    import import_from_feed

    monkeypatch.setattr(sys, "argv", ["import_from_feed.py", "--feed", "all"])
    monkeypatch.setattr(import_from_feed, "load_config", lambda: tmp_config)

    def feed_with_distinct_article(feed_url):
        return f"<rss><channel><item><title>Story</title><link>{feed_url}/story</link></item></channel></rss>"

    monkeypatch.setattr(import_from_feed, "fetch_feed", feed_with_distinct_article)
    sample_episode.audio_sha256 = hashlib.sha256(AUDIO).hexdigest()
    repo = EpisodeRepository(tmp_config.episodes_file)
    repo.add(sample_episode)
    download = pipeline.AudioDownloader.download
    attempts = []

    def download_audio(self, url, destination):
        attempts.append(url)
        if first_download_fails and len(attempts) == 1:
            raise pipeline.AudioDownloadError("connection lost")
        return download(self, url, destination)

    monkeypatch.setattr(pipeline.AudioDownloader, "download", download_audio)
    expected_attempts = 2 if first_download_fails else 1
    assert import_from_feed.main() == (1 if first_download_fails else 0)
    assert attempts == ["https://example.com/audio.mp3"] * expected_attempts

    # A later batch must verify the remote audio again.
    assert import_from_feed.main() == 0
    assert len(attempts) == expected_attempts + 1
    assert repo.load_all() == [sample_episode]
