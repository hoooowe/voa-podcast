"""Exercise --update against a previously published episode."""

import hashlib
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest

from voa_podcast.audio_downloader import AudioDownloadError
from voa_podcast.episode_repository import EpisodeRepository
from voa_podcast.models import Sentence, VOAArticle
from voa_podcast.rss_generator import RSSGenerator
from voa_podcast.site_generator import SiteGenerator
from voa_podcast.transcript_generator import TranscriptGenerator
from voa_podcast.translator import TranslationError
from voa_podcast.voa_fetcher import VOAFetchError


ORIGINAL_AUDIO = b"original MP3"
OTHER_AUDIO = b"another episode's MP3"
NEW_AUDIO = b"corrected MP3"


@pytest.fixture
def replacement_audio():
    return NEW_AUDIO


@pytest.fixture
def update_cli(monkeypatch, tmp_config, sample_episode, replacement_audio):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import add_episode

    other = replace(
        sample_episode, id=2, guid="voa-podcast-002", slug="another-story",
        source_url="https://learningenglish.voanews.com/a/another/456.html",
        audio_file="audio/002-another-story.mp3",
    )
    sample_episode.sentences = [Sentence(0, "Original timed caption.", "原字幕")]
    repo = EpisodeRepository(tmp_config.episodes_file)
    for episode, audio in [(sample_episode, ORIGINAL_AUDIO), (other, OTHER_AUDIO)]:
        episode.audio_sha256 = hashlib.sha256(audio).hexdigest()
        episode.audio_size = len(audio)
        (tmp_config.docs_dir / episode.audio_file).write_bytes(audio)
        repo.add(episode)
    SiteGenerator(tmp_config).generate(repo.load_all())
    TranscriptGenerator(tmp_config).generate_all(repo.load_all())
    RSSGenerator(tmp_config).generate(repo.load_all())

    article = VOAArticle(
        "Corrected title", sample_episode.source_url, sample_episode.published_at,
        "A corrected transcript.", "https://example.org/new.mp3",
    )
    monkeypatch.setattr(sys, "argv", ["add_episode.py", sample_episode.source_url, "--update"])
    monkeypatch.setattr(add_episode, "load_config", lambda: tmp_config)
    monkeypatch.setattr(add_episode.VOAContentFetcher, "fetch", lambda self, url: article)
    monkeypatch.setattr(add_episode.OpenAICompatibleTranslator, "translate", lambda self, text: "新译文")

    audio_response = Mock(status_code=200, headers={"Content-Type": "audio/mpeg"})
    audio_response.iter_content.return_value = [replacement_audio]
    monkeypatch.setattr("requests.Session.get", Mock(return_value=audio_response))
    return add_episode


def published_files(config):
    files = [config.episodes_file]
    files.extend(path for path in config.docs_dir.rglob("*") if path.is_file())
    return {path.relative_to(config.project_root): path.read_bytes() for path in files}


@pytest.mark.parametrize(
    ("method", "error"),
    [
        ("VOAContentFetcher.fetch", VOAFetchError),
        ("AudioDownloader.download", AudioDownloadError),
        ("OpenAICompatibleTranslator.translate", TranslationError),
        ("RSSGenerator.generate", OSError),
    ],
)
def test_update_failure_keeps_published_files(update_cli, tmp_config, monkeypatch, method, error):
    before = published_files(tmp_config)
    failure = Mock(side_effect=error("unavailable"))
    monkeypatch.setattr(f"add_episode.{method}", failure)

    assert update_cli.main() == 1
    failure.assert_called_once()
    assert published_files(tmp_config) == before


@pytest.mark.parametrize("replacement_audio", [OTHER_AUDIO])
def test_update_matching_another_episode_keeps_original(update_cli, tmp_config):
    before = published_files(tmp_config)
    assert update_cli.main() == 2
    assert published_files(tmp_config) == before


@pytest.mark.parametrize("replacement_audio", [b""])
def test_empty_audio_response_keeps_original(update_cli, tmp_config):
    before = published_files(tmp_config)
    assert update_cli.main() == 1
    assert published_files(tmp_config) == before


def test_unreadable_catalog_preserves_existing_files(update_cli, tmp_config):
    tmp_config.episodes_file.write_bytes(b'[{"id":')
    before = published_files(tmp_config)
    assert update_cli.main() == 1
    assert published_files(tmp_config) == before


def test_update_leaves_shared_mp3_for_other_episode(update_cli, tmp_config):
    repo = EpisodeRepository(tmp_config.episodes_file)
    original, other = repo.load_all()
    other.audio_file = original.audio_file
    other.audio_sha256 = original.audio_sha256
    other.audio_size = original.audio_size
    repo.save_all([original, other])

    assert update_cli.main() == 0
    updated = repo.find_by_url(original.source_url)
    assert updated.audio_file != other.audio_file
    assert (tmp_config.docs_dir / updated.audio_file).read_bytes() == NEW_AUDIO
    assert repo.find_by_url(other.source_url) == other
    assert (tmp_config.docs_dir / other.audio_file).read_bytes() == ORIGINAL_AUDIO


def test_update_rolls_back_if_episode_record_cannot_be_published(
    update_cli, tmp_config, sample_episode, monkeypatch
):
    before = published_files(tmp_config)
    audio = tmp_config.docs_dir / sample_episode.audio_file
    replace_file = Path.replace
    publication_attempts = []

    def fail_final_replace(path, target):
        if target == tmp_config.episodes_file and not publication_attempts:
            publication_attempts.append(audio.read_bytes())
            raise OSError("cannot publish episode record")
        return replace_file(path, target)

    monkeypatch.setattr(Path, "replace", fail_final_replace)
    assert update_cli.main() == 1
    assert publication_attempts == [NEW_AUDIO]
    assert published_files(tmp_config) == before
    assert update_cli.main() == 0


@pytest.mark.parametrize("replacement_audio", [NEW_AUDIO, ORIGINAL_AUDIO], ids=["new-mp3", "same-mp3"])
def test_update_refreshes_the_existing_episode(update_cli, tmp_config, sample_episode, replacement_audio):
    repo = EpisodeRepository(tmp_config.episodes_file)
    other = repo.load_all()[1]

    assert update_cli.main() == 0
    episodes = repo.load_all()
    assert len(episodes) == 2
    assert other in episodes
    updated = repo.find_by_url(sample_episode.source_url)
    assert updated is not None
    assert (updated.id, updated.guid, updated.slug) == (
        sample_episode.id, sample_episode.guid, sample_episode.slug,
    )
    assert updated.title == "Corrected title"
    assert updated.english_text == "A corrected transcript."
    assert updated.chinese_text == "新译文"
    assert updated.audio_size == len(replacement_audio)
    assert updated.audio_sha256 == hashlib.sha256(replacement_audio).hexdigest()
    assert updated.audio_file == sample_episode.audio_file
    assert (tmp_config.docs_dir / updated.audio_file).read_bytes() == replacement_audio
    assert (tmp_config.docs_dir / other.audio_file).read_bytes() == OTHER_AUDIO

    page = (tmp_config.episodes_html_dir / f"{updated.slug}.html").read_text(encoding="utf-8")
    assert updated.title in page
    assert updated.english_text in page
    assert updated.chinese_text in page
    audio_url = f"{tmp_config.site.site_url}/{updated.audio_file}"
    assert audio_url in page
    rss = ET.parse(tmp_config.docs_dir / "feed.xml")
    item = rss.find(f"./channel/item[guid='{updated.guid}']")
    assert item is not None
    assert item.findtext("title") == updated.title
    assert item.find("enclosure").get("url") == audio_url
