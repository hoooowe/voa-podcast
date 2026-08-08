"""Tests for VOA RSS feed parsing (offline)."""

from __future__ import annotations

from datetime import datetime, timezone

from voa_podcast.feed_parser import FeedItem, parse_feed

SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>American Stories - Voice of America</title>
    <link>https://learningenglish.voanews.com/z/1581</link>
    <description>Learn English as you read and listen to short stories.</description>
    <lastBuildDate>Sat, 08 Aug 2026 10:23:48 +0000</lastBuildDate>
    <item>
      <title>'The Open Boat' by Stephen Crane, Part Two</title>
      <description>We continue the story...</description>
      <link>https://learningenglish.voanews.com/a/open-boat-part-two/7504521.html</link>
      <guid>https://learningenglish.voanews.com/a/open-boat-part-two/7504521.html</guid>
      <pubDate>Fri, 14 Mar 2025 22:00:46 +0000</pubDate>
      <category>American Stories</category>
      <category>Lessons of the Day</category>
    </item>
    <item>
      <title>'The Open Boat' by Stephen Crane, Part One</title>
      <description>American Stories presents a short story...</description>
      <link>https://learningenglish.voanews.com/a/open-boat-part-one/2572601.html</link>
      <guid>https://learningenglish.voanews.com/a/open-boat-part-one/2572601.html</guid>
      <pubDate>Fri, 07 Mar 2025 22:00:00 +0000</pubDate>
      <category>American Stories</category>
    </item>
    <item>
      <title>Item with no link</title>
      <pubDate>Sat, 01 Jan 2025 00:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""


def test_parse_feed_returns_items_with_link():
    items = parse_feed(SAMPLE_FEED)
    # 3 items in feed, but the one without <link> is skipped.
    assert len(items) == 2


def test_parse_feed_title():
    items = parse_feed(SAMPLE_FEED)
    assert items[0].title == "'The Open Boat' by Stephen Crane, Part Two"
    assert items[1].title == "'The Open Boat' by Stephen Crane, Part One"


def test_parse_feed_url():
    items = parse_feed(SAMPLE_FEED)
    assert items[0].url == (
        "https://learningenglish.voanews.com/a/open-boat-part-two/7504521.html"
    )


def test_parse_feed_published_at():
    items = parse_feed(SAMPLE_FEED)
    assert items[0].published_at == datetime(2025, 3, 14, 22, 0, 46, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 3, 7, 22, 0, 0, tzinfo=timezone.utc)


def test_parse_feed_categories():
    items = parse_feed(SAMPLE_FEED)
    assert items[0].categories == ["American Stories", "Lessons of the Day"]
    assert items[1].categories == ["American Stories"]


def test_parse_feed_skips_item_without_link():
    items = parse_feed(SAMPLE_FEED)
    assert all(item.url for item in items)
    assert not any("no link" in item.title.lower() for item in items)


def test_parse_feed_empty_channel():
    items = parse_feed("<rss version=\"2.0\"><channel></channel></rss>")
    assert items == []


def test_parse_feed_no_channel_element():
    items = parse_feed("<rss version=\"2.0\"></rss>")
    assert items == []


def test_parse_feed_invalid_date_is_none():
    xml = (
        '<rss version="2.0"><channel>'
        "<item><title>T</title>"
        "<link>http://example.com/a</link>"
        "<pubDate>not a real date</pubDate>"
        "</item></channel></rss>"
    )
    items = parse_feed(xml)
    assert len(items) == 1
    assert items[0].published_at is None


def test_parse_feed_missing_pubdate():
    xml = (
        '<rss version="2.0"><channel>'
        "<item><title>No Date</title>"
        "<link>http://example.com/b</link>"
        "</item></channel></rss>"
    )
    items = parse_feed(xml)
    assert len(items) == 1
    assert items[0].published_at is None


def test_parse_feed_empty_categories():
    xml = (
        '<rss version="2.0"><channel>'
        "<item><title>T</title>"
        "<link>http://example.com/c</link>"
        "</item></channel></rss>"
    )
    items = parse_feed(xml)
    assert items[0].categories == []


def test_parse_feed_invalid_xml_returns_empty():
    items = parse_feed("not valid xml <<<")
    assert items == []


def test_feed_item_is_dataclass():
    item = FeedItem(title="T", url="http://x", published_at=None, categories=[])
    assert item.title == "T"
    assert item.url == "http://x"
    assert item.published_at is None
    assert item.categories == []
