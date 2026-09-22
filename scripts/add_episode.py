#!/usr/bin/env python3
"""Add a VOA Learning English article as a new podcast episode.

Usage:
    python scripts/add_episode.py "VOA_URL" [--force]
"""

from __future__ import annotations

import argparse
import logging
import re
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

GENERIC_TITLES = {
    "voa learning english podcast",
    "learning english podcast",
    "american stories",
}


def _audio_date(audio_url: str) -> str | None:
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", audio_url or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(20\d{2})(\d{2})(\d{2})-\d{6}", audio_url or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def refine_title(title: str, audio_url: str, series: str | None = None) -> str:
    """Turn generic series titles into something per-episode readable."""
    title = (title or "").strip()
    if title.lower() not in GENERIC_TITLES:
        return title
    date = _audio_date(audio_url or "")
    base = (series or title).strip() or title
    return f"{base} ({date})" if date else base


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


def run_pipeline(
    url: str,
    force: bool = False,
    update: bool = False,
    category: str | None = None,
    title: str | None = None,
) -> int:
    """Process one article URL. Return codes: 0=created/skipped-ok, 2=duplicate, 1=failed."""
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
    if category and not article.category:
        article.category = category
    article.title = refine_title(
        title or article.title,
        article.audio_url,
        series=category or title,
    )

    # 3. Copyright check.
    checker = CopyrightChecker()
    result = checker.check(article)
    if result.status == CopyrightStatus.THIRD_PARTY:
        if config.copyright_strict:
            logger.error(
                "[COPYRIGHT] Third-party content (%s). Not processing.",
                result.matched_source,
            )
            return 1
        logger.warning(
            "[COPYRIGHT] Third-party content (%s). copyright.strict=false, proceeding.",
            result.matched_source,
        )
    if result.status == CopyrightStatus.UNKNOWN and not force:
        logger.error(
            "[COPYRIGHT] Unknown copyright source. Use --force to proceed manually."
        )
        return 1

    # 4. Download audio.
    downloader = AudioDownloader()
    episode_title = article.title
    slug = make_slug(episode_title)
    episode_id = repo.next_id()
    filename = audio_filename(episode_id, slug)
    audio_path = config.audio_dir / filename
    audio_meta = downloader.download(article.audio_url, audio_path)

    try:
        # Auxiliary duplicate check via audio SHA256.
        # Same episode often appears under multiple feed URLs — treat as skip, not error.
        dupe_audio = repo.find_by_audio_sha256(audio_meta.sha256)
        if dupe_audio is not None:
            logger.warning(
                "[AUDIO] Duplicate audio (SHA256 matches episode #%d). Skipping.",
                dupe_audio.id,
            )
            return 2

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
    except Exception:
        # Don't leave half-downloaded audio behind when translation/build fails.
        audio_path.unlink(missing_ok=True)
        raise

    # 7. Rebuild site + transcripts + RSS.
    episodes = repo.load_all()
    SiteGenerator(config).generate(episodes)
    from voa_podcast.transcript_generator import TranscriptGenerator

    TranscriptGenerator(config).generate_all(episodes)
    RSSGenerator(config).generate(episodes)

    # 8. Output.
    print()
    print("Episode created successfully")
    print()
    print(f"Title:  {episode.title}")
    print(f"Audio:  docs/{episode.audio_file}")
    print(f"Page:   docs/episodes/{episode.slug}.html")
    print(f"Podcast Feed: docs/feed.xml")
    print()
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
