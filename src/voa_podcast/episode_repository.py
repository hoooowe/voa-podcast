"""Episode repository backed by data/episodes.json.

This is the single source of truth for the MVP (no database). Handles
persistence, slug/GUID generation, and duplicate detection by source_url.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import Episode

logger = logging.getLogger(__name__)

MAX_SLUG_WORDS = 8


class EpisodeRepository:
    """Loads and persists episodes to a JSON file."""

    def __init__(self, episodes_file: Path) -> None:
        self._file = episodes_file
        self._file.parent.mkdir(parents=True, exist_ok=True)
        if not self._file.exists():
            self._file.write_text("[]", encoding="utf-8")

    def load_all(self) -> list[Episode]:
        """Load all episodes from the JSON file."""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("[REPO] Failed to read episodes.json: %s", exc)
            return []
        return [Episode.from_dict(item) for item in data]

    def save_all(self, episodes: list[Episode]) -> None:
        """Persist all episodes to the JSON file."""
        data = [ep.to_dict() for ep in episodes]
        self._file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def find_by_url(self, source_url: str) -> Episode | None:
        """Return an existing episode with the given source_url, if any."""
        for ep in self.load_all():
            if ep.source_url == source_url:
                return ep
        return None

    def find_by_audio_sha256(self, sha256: str) -> Episode | None:
        """Return an existing episode with a matching audio SHA256, if any."""
        for ep in self.load_all():
            if ep.audio_sha256 and ep.audio_sha256 == sha256:
                return ep
        return None

    def remove_by_url(self, source_url: str) -> Episode | None:
        """Remove and return the episode with the given source_url, if any."""
        episodes = self.load_all()
        for i, ep in enumerate(episodes):
            if ep.source_url == source_url:
                del episodes[i]
                self.save_all(episodes)
                return ep
        return None

    def next_id(self) -> int:
        """Return the next episode id (1-based)."""
        episodes = self.load_all()
        if not episodes:
            return 1
        return max(ep.id for ep in episodes) + 1

    def add(self, episode: Episode) -> None:
        """Append an episode and persist."""
        episodes = self.load_all()
        episodes.append(episode)
        self.save_all(episodes)

    def create_episode(
        self,
        *,
        title: str,
        slug: str | None,
        source_url: str,
        published_at: datetime | None,
        category: str | None,
        english_text: str,
        chinese_text: str,
        audio_file: str,
        audio_size: int,
        audio_type: str,
        audio_sha256: str,
        copyright_status: str,
        source: str = "VOA Learning English",
        sentences: list | None = None,
    ) -> Episode:
        """Build a new Episode with a stable id, GUID, and slug."""
        episode_id = self.next_id()
        final_slug = slug or make_slug(title)
        # Ensure slug uniqueness against existing episodes.
        final_slug = self._ensure_unique_slug(final_slug)
        guid = f"voa-podcast-{episode_id:03d}"
        now = datetime.now(timezone.utc)

        episode = Episode(
            id=episode_id,
            guid=guid,
            title=title,
            slug=final_slug,
            source=source,
            source_url=source_url,
            published_at=published_at,
            created_at=now,
            category=category,
            english_text=english_text,
            chinese_text=chinese_text,
            audio_file=audio_file,
            audio_size=audio_size,
            audio_type=audio_type,
            audio_sha256=audio_sha256,
            copyright_status=copyright_status,
            sentences=sentences or [],
        )
        self.add(episode)
        return episode

    def _ensure_unique_slug(self, slug: str) -> str:
        existing = {ep.slug for ep in self.load_all()}
        if slug not in existing:
            return slug
        n = 2
        while f"{slug}-{n}" in existing:
            n += 1
        return f"{slug}-{n}"


def make_slug(title: str) -> str:
    """Generate an ASCII slug from a title."""
    # Keep ASCII letters/digits, replace the rest with hyphens.
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()
    words = [w for w in slug.split("-") if w]
    if len(words) > MAX_SLUG_WORDS:
        words = words[:MAX_SLUG_WORDS]
    slug = "-".join(words)
    return slug or "episode"


def audio_filename(episode_id: int, slug: str) -> str:
    """Return the local audio filename, e.g. ``001-ai-and-education.mp3``."""
    return f"{episode_id:03d}-{slug}.mp3"
