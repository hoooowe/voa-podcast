"""Parser for VOA Learning English RSS feeds.

Parses standard RSS 2.0 XML (as served by learningenglish.voanews.com)
into a list of :class:`FeedItem` objects, each pointing to an article URL
that can be fed into the existing ``add_episode`` pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


@dataclass
class FeedItem:
    """A single item parsed from a VOA RSS feed."""

    title: str
    url: str
    published_at: datetime | None
    categories: list[str]


def parse_feed(xml_text: str) -> list[FeedItem]:
    """Parse a VOA RSS feed XML string into a list of :class:`FeedItem`.

    Items without a ``<link>`` element are skipped (they have no article
    URL to fetch).  Malformed dates are tolerated (``published_at`` becomes
    ``None``).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.error("[FEED] XML parse error: %s", exc)
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    items: list[FeedItem] = []
    for item_el in channel.findall("item"):
        title = (item_el.findtext("title") or "").strip()
        link = (item_el.findtext("link") or "").strip()
        if not link:
            continue

        pub_raw = (item_el.findtext("pubDate") or "").strip()
        published_at = _parse_rfc822(pub_raw) if pub_raw else None

        categories = [
            (c.text or "").strip()
            for c in item_el.findall("category")
            if (c.text or "").strip()
        ]

        items.append(
            FeedItem(
                title=title,
                url=link,
                published_at=published_at,
                categories=categories,
            )
        )
    return items


def _parse_rfc822(raw: str) -> datetime | None:
    """Parse an RFC 822 date string (e.g. ``Fri, 14 Mar 2025 22:00:46 +0000``)."""
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
