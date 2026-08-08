#!/usr/bin/env python3
"""Rebuild the static site (HTML + RSS feed) from episodes.json.

Usage:
    python scripts/build_site.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from voa_podcast.config import load_config
from voa_podcast.episode_repository import EpisodeRepository
from voa_podcast.rss_generator import RSSGenerator
from voa_podcast.site_generator import SiteGenerator

logger = logging.getLogger("build_site")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = load_config()

    repo = EpisodeRepository(config.episodes_file)
    episodes = repo.load_all()

    SiteGenerator(config).generate(episodes)
    RSSGenerator(config).generate(episodes)

    print(f"Site rebuilt with {len(episodes)} episode(s).")
    print(f"  Index: docs/index.html")
    print(f"  Feed:  docs/feed.xml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
