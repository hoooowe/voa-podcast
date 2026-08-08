"""Static site generator using Jinja2 templates.

Renders docs/index.html and docs/episodes/{slug}.html from episodes.json.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import AppConfig
from .models import Episode

logger = logging.getLogger(__name__)


class SiteGenerator:
    """Generates the static HTML site from episodes."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._env = Environment(
            loader=FileSystemLoader(str(config.templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(self, episodes: list[Episode]) -> None:
        """Render the index page and every episode page."""
        self._config.episodes_html_dir.mkdir(parents=True, exist_ok=True)
        self._generate_index(episodes)
        for ep in episodes:
            self._generate_episode_page(ep)
        logger.info("[SITE] Generated %d episode pages.", len(episodes))

    def _generate_index(self, episodes: list[Episode]) -> None:
        template = self._env.get_template("index.html.j2")
        sorted_episodes = sorted(
            episodes,
            key=lambda e: e.created_at,
            reverse=True,
        )
        view_models = [self._episode_summary(e) for e in sorted_episodes]
        html = template.render(
            site_title=self._config.site.title,
            feed_url=self._feed_url(),
            episodes=view_models,
        )
        out = self._config.docs_dir / "index.html"
        out.write_text(html, encoding="utf-8")
        logger.info("[SITE] Index generated.")

    def _generate_episode_page(self, episode: Episode) -> None:
        template = self._env.get_template("episode.html.j2")
        vm = self._episode_detail(episode)
        html = template.render(
            site_title=self._config.site.title,
            episode=vm,
        )
        out = self._config.episodes_html_dir / f"{episode.slug}.html"
        out.write_text(html, encoding="utf-8")

    # ------------------------------------------------------------------ #
    # View models
    # ------------------------------------------------------------------ #
    def _episode_summary(self, ep: Episode) -> dict:
        return {
            "id": ep.id,
            "title": ep.title,
            "slug": ep.slug,
            "category": ep.category,
            "published_at_display": _format_date(ep.published_at),
            "audio_url": self._audio_url(ep.audio_file),
        }

    def _episode_detail(self, ep: Episode) -> dict:
        return {
            "title": ep.title,
            "slug": ep.slug,
            "category": ep.category,
            "published_at_display": _format_date(ep.published_at),
            "source_url": ep.source_url,
            "source": ep.source,
            "audio_url": self._audio_url(ep.audio_file),
            "english_paragraphs": _split_paragraphs(ep.english_text),
            "chinese_paragraphs": _split_paragraphs(ep.chinese_text),
        }

    # ------------------------------------------------------------------ #
    # URL helpers
    # ------------------------------------------------------------------ #
    def _audio_url(self, audio_file: str) -> str:
        # audio_file is stored relative to docs/, e.g. "audio/001-x.mp3"
        return f"{self._config.site.site_url}/{audio_file.lstrip('/')}"

    def _feed_url(self) -> str:
        return f"{self._config.site.site_url}/feed.xml"


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _format_date(dt: datetime | None) -> str:
    if dt is None:
        return "Unknown date"
    return dt.strftime("%b %d, %Y")
