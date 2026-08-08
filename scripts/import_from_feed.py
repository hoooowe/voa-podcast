#!/usr/bin/env python3
"""Import podcast episodes from VOA Learning English RSS feeds.

Fetches a VOA RSS feed, extracts article URLs, and processes each one
through the same pipeline as ``add_episode.py`` (fetch → parse → copyright
check → download audio → translate → create episode → rebuild site/RSS).

Designed to run on GitHub Actions (US servers) where learningenglish.
voanews.com is directly accessible.

Usage:
    python scripts/import_from_feed.py --feed american-stories [--limit 3]
    python scripts/import_from_feed.py --feed learning-english-podcast [--limit 3]
    python scripts/import_from_feed.py --feed all [--limit 3]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make the src package and scripts dir importable when running directly.
_SRC = Path(__file__).resolve().parents[1] / "src"
_SCRIPTS = Path(__file__).resolve().parent
for _p in (_SRC, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import requests  # noqa: E402

from voa_podcast.config import load_config  # noqa: E402
from voa_podcast.episode_repository import EpisodeRepository  # noqa: E402
from voa_podcast.feed_parser import parse_feed  # noqa: E402

# Reuse the full add_episode pipeline (fetch/parse/translate/build).
from add_episode import run_pipeline  # noqa: E402

logger = logging.getLogger("import_from_feed")

FEEDS: dict[str, dict[str, str]] = {
    "american-stories": {
        "name": "American Stories",
        "url": "https://learningenglish.voanews.com/api/zyg__l-vomx-tpetmty",
    },
    "learning-english-podcast": {
        "name": "VOA Learning English Podcast",
        "url": "https://learningenglish.voanews.com/api/ziiy_l-vomx-tpemgtv",
    },
}

DEFAULT_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import VOA Learning English episodes from RSS feeds."
    )
    parser.add_argument(
        "--feed",
        choices=["american-stories", "learning-english-podcast", "all"],
        default="all",
        help="Which feed to import from (default: all).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum number of new episodes to import per feed (default: 3).",
    )
    return parser.parse_args()


def fetch_feed(url: str) -> str:
    """Download the raw RSS XML for a feed URL."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def main() -> int:
    setup_logging()
    args = parse_args()

    feed_keys = list(FEEDS) if args.feed == "all" else [args.feed]

    config = load_config()
    repo = EpisodeRepository(config.episodes_file)

    total_added = 0
    total_skipped = 0
    total_failed = 0

    for key in feed_keys:
        feed = FEEDS[key]
        logger.info("")
        logger.info("=== Feed: %s ===", feed["name"])
        try:
            xml_text = fetch_feed(feed["url"])
        except requests.RequestException as exc:
            logger.error("[FEED] Failed to fetch %s: %s", feed["name"], exc)
            total_failed += 1
            continue

        items = parse_feed(xml_text)
        logger.info("[FEED] Found %d items.", len(items))

        added = 0
        for item in items:
            if added >= args.limit:
                break

            # Skip episodes that already exist (avoids unnecessary fetching).
            if repo.find_by_url(item.url) is not None:
                logger.info("[SKIP] Already imported: %s", item.title)
                total_skipped += 1
                continue

            logger.info("")
            logger.info("[IMPORT] %s", item.title)
            logger.info("[IMPORT] URL: %s", item.url)

            try:
                rc = run_pipeline(item.url, force=False, update=False)
            except Exception as exc:  # noqa: BLE001
                logger.error("[IMPORT] FAILED: %s", exc)
                total_failed += 1
                continue

            if rc == 0:
                added += 1
                total_added += 1
            else:
                logger.warning("[IMPORT] Pipeline returned rc=%d, skipping.", rc)
                total_failed += 1

    logger.info("")
    logger.info("=== Import Summary ===")
    logger.info("Added:    %d", total_added)
    logger.info("Skipped:  %d", total_skipped)
    logger.info("Failed:   %d", total_failed)
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
