"""Tests for Podcast RSS generation."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from voa_podcast.models import Episode
from voa_podcast.rss_generator import RSSGenerator

NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def _generate(tmp_config, episodes):
    path = RSSGenerator(tmp_config).generate(episodes)
    return ET.parse(path)


def test_feed_is_wellformed(tmp_config, sample_episode):
    tree = _generate(tmp_config, [sample_episode])
    root = tree.getroot()
    assert root.tag == "rss"
    assert root.get("version") == "2.0"


def test_channel_required_fields(tmp_config, sample_episode):
    tree = _generate(tmp_config, [sample_episode])
    channel = tree.getroot().find("channel")
    assert channel is not None
    assert channel.findtext("title") == "Daily English Listening"
    assert channel.findtext("link", "").startswith("https://tester.github.io")
    assert channel.findtext("description")
    assert channel.findtext("language") == "en-us"
    assert channel.find("itunes:block", NS) is not None


def test_itunes_block_is_yes(tmp_config, sample_episode):
    tree = _generate(tmp_config, [sample_episode])
    channel = tree.getroot().find("channel")
    assert channel.find("itunes:block", NS).text == "Yes"


def test_item_enclosure_url(tmp_config, sample_episode):
    tree = _generate(tmp_config, [sample_episode])
    item = tree.getroot().find("channel/item")
    assert item is not None
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.get("url") == (
        "https://tester.github.io/voa-podcast/audio/001-ai-is-changing-education.mp3"
    )
    assert enclosure.get("type") == "audio/mpeg"
    assert int(enclosure.get("length")) == 12345678


def test_item_guid_stable_and_not_permalink(tmp_config, sample_episode):
    tree = _generate(tmp_config, [sample_episode])
    item = tree.getroot().find("channel/item")
    guid = item.find("guid")
    assert guid.text == "voa-podcast-001"
    assert guid.get("isPermaLink") == "false"


def test_item_has_content_encoded(tmp_config, sample_episode):
    tree = _generate(tmp_config, [sample_episode])
    item = tree.getroot().find("channel/item")
    encoded = item.find("content:encoded", NS)
    assert encoded is not None
    assert "English Original" in encoded.text
    assert "中文翻译" in encoded.text
    assert "Read full transcript" not in encoded.text  # short article


def test_long_description_truncated_with_link(tmp_config):
    long_en = "\n\n".join([f"Paragraph number {i} " * 20 for i in range(60)])
    long_zh = "\n\n".join([f"第 {i} 段 " * 20 for i in range(60)])
    ep = Episode(
        id=2,
        guid="voa-podcast-002",
        title="Long Article",
        slug="long-article",
        source="VOA Learning English",
        source_url="https://learningenglish.voanews.com/a/long/1.html",
        published_at=None,
        created_at=__import__("datetime").datetime(2026, 8, 9, tzinfo=__import__("datetime").timezone.utc),
        category="Science",
        english_text=long_en,
        chinese_text=long_zh,
        audio_file="audio/002-long-article.mp3",
        audio_size=999,
        audio_type="audio/mpeg",
        copyright_status="VOA_ORIGINAL",
    )
    tree = _generate(tmp_config, [ep])
    item = tree.getroot().find("channel/item")
    encoded = item.find("content:encoded", NS)
    assert "Read full transcript" in encoded.text


def test_feed_empty_episodes(tmp_config):
    tree = _generate(tmp_config, [])
    items = tree.getroot().findall("channel/item")
    assert items == []
