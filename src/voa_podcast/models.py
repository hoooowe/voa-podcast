"""Core data models for VOA articles, episodes, and copyright status."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class CopyrightStatus(str, Enum):
    VOA_ORIGINAL = "VOA_ORIGINAL"
    THIRD_PARTY = "THIRD_PARTY"
    UNKNOWN = "UNKNOWN"


@dataclass
class VOAArticle:
    """Raw article extracted from a VOA Learning English page."""

    title: str
    source_url: str
    published_at: datetime | None
    english_text: str
    audio_url: str
    category: str | None = None
    author: str | None = None
    copyright_source: str | None = None


@dataclass
class CopyrightResult:
    """Result of a copyright check on a VOA article."""

    status: CopyrightStatus
    matched_source: str | None = None
    reason: str = ""


@dataclass
class AudioMetadata:
    """Metadata for a downloaded audio file."""

    local_path: Path
    file_size: int
    mime_type: str
    sha256: str


@dataclass
class Episode:
    """A persisted podcast episode."""

    id: int
    guid: str
    title: str
    slug: str
    source: str
    source_url: str
    published_at: datetime | None
    created_at: datetime
    category: str | None
    english_text: str
    chinese_text: str
    audio_file: str
    audio_size: int
    audio_type: str
    audio_sha256: str = ""
    copyright_status: str = CopyrightStatus.VOA_ORIGINAL.value

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "guid": self.guid,
            "title": self.title,
            "slug": self.slug,
            "source": self.source,
            "source_url": self.source_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat(),
            "category": self.category,
            "english_text": self.english_text,
            "chinese_text": self.chinese_text,
            "audio_file": self.audio_file,
            "audio_size": self.audio_size,
            "audio_type": self.audio_type,
            "audio_sha256": self.audio_sha256,
            "copyright_status": self.copyright_status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        published_at = None
        if data.get("published_at"):
            published_at = datetime.fromisoformat(data["published_at"])
        created_at = datetime.fromisoformat(data["created_at"])
        return cls(
            id=data["id"],
            guid=data["guid"],
            title=data["title"],
            slug=data["slug"],
            source=data["source"],
            source_url=data["source_url"],
            published_at=published_at,
            created_at=created_at,
            category=data.get("category"),
            english_text=data["english_text"],
            chinese_text=data["chinese_text"],
            audio_file=data["audio_file"],
            audio_size=data["audio_size"],
            audio_type=data["audio_type"],
            audio_sha256=data.get("audio_sha256", ""),
            copyright_status=data.get("copyright_status", CopyrightStatus.VOA_ORIGINAL.value),
        )
