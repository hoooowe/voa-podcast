#!/usr/bin/env python3
"""Validate the generated Podcast RSS feed (docs/feed.xml).

Checks:
    - XML is well-formed.
    - Required channel fields present (title, link, description, language).
    - itunes:block present.
    - Each item has guid, enclosure (url/length/type), title, pubDate.
    - enclosure length is a positive integer.

Usage:
    python scripts/validate_feed.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from voa_podcast.config import load_config

NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def main() -> int:
    config = load_config()
    feed_path = config.docs_dir / "feed.xml"
    if not feed_path.exists():
        print(f"FAILED: feed not found at {feed_path}")
        return 1

    errors: list[str] = []

    try:
        tree = ET.parse(feed_path)
    except ET.ParseError as exc:
        print(f"FAILED: feed.xml is not well-formed XML: {exc}")
        return 1

    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        errors.append("Missing <channel> element.")

    if channel is not None:
        for required in ("title", "link", "description", "language"):
            if channel.find(required) is None:
                errors.append(f"Channel missing <{required}>.")
        if channel.find("itunes:block", NS) is None:
            errors.append("Channel missing <itunes:block>.")

        items = channel.findall("item")
        if not items:
            print("WARNING: feed has no episodes (valid but empty).")

        for idx, item in enumerate(items, start=1):
            title = item.findtext("title")
            if not title:
                errors.append(f"Item #{idx} missing <title>.")
            guid = item.findtext("guid")
            if not guid:
                errors.append(f"Item #{idx} missing <guid>.")
            if item.find("pubDate") is None:
                errors.append(f"Item #{idx} missing <pubDate>.")
            enclosure = item.find("enclosure")
            if enclosure is None:
                errors.append(f"Item #{idx} missing <enclosure>.")
            else:
                url = enclosure.get("url")
                length = enclosure.get("length")
                atype = enclosure.get("type")
                if not url:
                    errors.append(f"Item #{idx} enclosure missing url.")
                if not atype:
                    errors.append(f"Item #{idx} enclosure missing type.")
                if not length or not length.isdigit() or int(length) <= 0:
                    errors.append(
                        f"Item #{idx} enclosure length invalid: {length!r}"
                    )

    if errors:
        print("FAILED: feed validation errors:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("OK: feed.xml is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
