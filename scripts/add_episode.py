#!/usr/bin/env python3
"""Add a VOA Learning English article as a new podcast episode.

Usage:
    python scripts/add_episode.py "VOA_URL" [--force]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make the src package importable when running the script directly.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from voa_podcast.audio_downloader import AudioDownloadError, AudioDownloader
from voa_podcast.config import load_config
from voa_podcast.content_parser import VOAParseError
from voa_podcast.copyright_checker import CopyrightChecker
from voa_podcast.episode_repository import EpisodeRepository, audio_filename, make_slug
from voa_podcast.models import CopyrightStatus, Sentence
from voa_podcast.rss_generator import RSSGenerator
from voa_podcast.site_generator import SiteGenerator
from voa_podcast.translator import OpenAICompatibleTranslator, TranslationError
from voa_podcast.voa_fetcher import VOAContentFetcher, VOAFetchError

logger = logging.getLogger("add_episode")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add a VOA Learning English article as a podcast episode."
    )
    parser.add_argument("url", help="VOA Learning English article URL")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force processing even when copyright status is UNKNOWN.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Re-process an existing episode (deletes the old one and its audio first).",
    )
    return parser.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()

    try:
        return run_pipeline(args.url, force=args.force, update=args.update)
    except (
        VOAFetchError,
        VOAParseError,
        AudioDownloadError,
        TranslationError,
    ) as exc:
        logger.error("FAILED: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.error("FAILED (unexpected): %s", exc)
        return 1


def run_pipeline(url: str, force: bool = False, update: bool = False) -> int:
    config = load_config()

    # 1. Duplicate detection / update.
    repo = EpisodeRepository(config.episodes_file)
    existing = repo.find_by_url(url)
    if existing is not None:
        if not update:
            print("Episode already exists.")
            print(f"  Title: {existing.title}")
            print(f"  GUID:  {existing.guid}")
            print("  Use --update to re-process it.")
            return 0
        logger.info("[UPDATE] Removing existing episode #%d (%s).", existing.id, existing.guid)
        repo.remove_by_url(url)
        # Remove the old audio file; stale episode page is overwritten later.
        (config.docs_dir / existing.audio_file).unlink(missing_ok=True)

    # 2. Fetch + parse.
    fetcher = VOAContentFetcher()
    article = fetcher.fetch(url)

    # 3. Copyright check.
    checker = CopyrightChecker()
    result = checker.check(article)
    if result.status == CopyrightStatus.THIRD_PARTY:
        logger.error(
            "[COPYRIGHT] Third-party content (%s). Not processing.",
            result.matched_source,
        )
        return 1
    if result.status == CopyrightStatus.UNKNOWN and not force:
        logger.error(
            "[COPYRIGHT] Unknown copyright source. Use --force to proceed manually."
        )
        return 1

    # 4. Download audio.
    downloader = AudioDownloader()
    slug = make_slug(article.title)
    episode_id = repo.next_id()
    filename = audio_filename(episode_id, slug)
    audio_path = config.audio_dir / filename
    audio_meta = downloader.download(article.audio_url, audio_path)

    # Auxiliary duplicate check via audio SHA256.
    dupe_audio = repo.find_by_audio_sha256(audio_meta.sha256)
    if dupe_audio is not None:
        logger.error(
            "[AUDIO] Duplicate audio (SHA256 matches episode #%d). Skipping.",
            dupe_audio.id,
        )
        audio_path.unlink(missing_ok=True)
        return 1

    # 5. Translate.
    translator = OpenAICompatibleTranslator(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        model=config.llm.model,
        temperature=config.llm.temperature,
        max_chars_per_request=config.llm.max_chars_per_request,
        cache_dir=config.cache_dir,
    )

    episode_sentences: list[Sentence] = []
    if article.sentences:
        en_list = [s.en for s in article.sentences]
        zh_list = translator.translate_sentences(en_list)
        episode_sentences = [
            Sentence(start=s.start, en=s.en, zh=zh)
            for s, zh in zip(article.sentences, zh_list)
        ]
        chinese_text = "\n\n".join(s.zh for s in episode_sentences)
    else:
        chinese_text = translator.translate(article.english_text)

    # 6. Create episode.
    audio_rel = f"audio/{filename}"
    episode = repo.create_episode(
        title=article.title,
        slug=slug,
        source_url=article.source_url,
        published_at=article.published_at,
        category=article.category,
        english_text=article.english_text,
        chinese_text=chinese_text,
        audio_file=audio_rel,
        audio_size=audio_meta.file_size,
        audio_type=audio_meta.mime_type,
        audio_sha256=audio_meta.sha256,
        copyright_status=result.status.value,
        sentences=episode_sentences,
    )

    # 7. Rebuild site + RSS.
    episodes = repo.load_all()
    SiteGenerator(config).generate(episodes)
    RSSGenerator(config).generate(episodes)

    # 8. Output.
    print()
    print("Episode created successfully")
    print()
    print(f"Title:  {episode.title}")
    print(f"Audio:  docs/{episode.audio_file}")
    print(f"Page:   docs/episodes/{episode.slug}.html")
    print(f"Podcast Feed: docs/feed.xml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
