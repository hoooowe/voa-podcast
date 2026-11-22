"""Regression cases for the VOA roundup listed alongside playable episodes."""

import logging
import sys
from pathlib import Path

import pytest

from voa_podcast.episode_repository import EpisodeRepository


ARTICLE_URL = "https://learningenglish.voanews.com/a/learning-english-podcast/8010843.html"
ARTICLE = """
<script type="application/ld+json">
{"@type":"NewsArticle","headline":"Learning English Podcast"}
</script>
<div class="cover-media"><figure><img src="/cover.jpg"></figure></div>
<div id="article-content"><div class="wsw"><p>Related stories from the program.</p></div></div>
"""


@pytest.mark.parametrize(
    ("html", "expected_status"),
    [
        pytest.param(ARTICLE, 0, id="text-only-roundup"),
        pytest.param(ARTICLE + "<audio></audio>", 1, id="unresolved-player"),
        pytest.param("<h1>Error page</h1><p>Try again later.</p>", 1, id="unexpected-page"),
    ],
)
def test_feed_without_new_audio(html, expected_status, monkeypatch, tmp_config, sample_episode, caplog):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import add_episode
    import import_from_feed

    monkeypatch.setattr(sys, "argv", ["import_from_feed.py", "--feed", "learning-english-podcast"])
    monkeypatch.setattr(import_from_feed, "load_config", lambda: tmp_config)
    monkeypatch.setattr(add_episode, "load_config", lambda: tmp_config)
    monkeypatch.setattr(add_episode.VOAContentFetcher, "fetch_html", lambda self, url: html)
    feed = f"""<rss><channel><item>
        <title>Learning English Podcast</title><link>{ARTICLE_URL}</link>
        <enclosure url="https://example.org/cover.jpg" type="image/jpeg" length="0" />
    </item></channel></rss>"""
    monkeypatch.setattr(import_from_feed, "fetch_feed", lambda url: feed)
    repo = EpisodeRepository(tmp_config.episodes_file)
    repo.add(sample_episode)
    published = tmp_config.docs_dir / "feed.xml"
    published.write_text("<rss/>", encoding="utf-8")

    with caplog.at_level(logging.INFO):
        assert import_from_feed.main() == expected_status
    assert f"Skipped:  {1 - expected_status}" in caplog.messages
    assert f"Failed:   {expected_status}" in caplog.messages
    assert repo.load_all() == [sample_episode]
    assert published.read_text(encoding="utf-8") == "<rss/>"
