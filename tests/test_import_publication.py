import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from voa_podcast.episode_repository import EpisodeRepository


@pytest.fixture
def partial_import(monkeypatch, tmp_config, sample_episode):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import import_from_feed

    monkeypatch.setattr(sys, "argv", ["import_from_feed.py", "--feed", "american-stories"])
    monkeypatch.setattr(import_from_feed, "load_config", lambda: tmp_config)
    feed = f"""<rss><channel>
        <item><title>Unavailable</title><link>https://example.org/missing</link></item>
        <item><title>Available</title><link>{sample_episode.source_url}</link></item>
    </channel></rss>"""
    monkeypatch.setattr(import_from_feed, "fetch_feed", lambda url: feed)

    def import_article(url, **kwargs):
        if url != sample_episode.source_url:
            return 1
        EpisodeRepository(tmp_config.episodes_file).add(sample_episode)
        return 0

    monkeypatch.setattr(import_from_feed, "run_pipeline", import_article)
    return import_from_feed


def test_partial_import_is_publishable_after_rebuild(partial_import, tmp_config, sample_episode):
    assert partial_import.main() == 0
    channel = ET.parse(tmp_config.docs_dir / "feed.xml")
    assert channel.findtext("channel/item/guid") == sample_episode.guid


def test_partial_import_fails_if_final_rebuild_fails(partial_import, monkeypatch):
    def fail_rebuild(self, episodes):
        raise OSError("Unable to write feed")

    monkeypatch.setattr(partial_import.RSSGenerator, "generate", fail_rebuild)
    assert partial_import.main() == 1
