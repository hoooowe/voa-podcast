"""Shared pytest fixtures."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from voa_podcast.config import AppConfig, LLMConfig, PodcastConfig, SiteConfig
from voa_podcast.models import Episode

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def voa_html() -> str:
    return (FIXTURES_DIR / "voa_article.html").read_text(encoding="utf-8")


@pytest.fixture
def tmp_config(tmp_path: Path) -> AppConfig:
    """An AppConfig rooted in a temp directory with templates available."""
    project_root = Path(__file__).resolve().parents[1]
    templates_dir = project_root / "templates"

    # Copy templates into temp so site generation is isolated.
    tmp_templates = tmp_path / "templates"
    tmp_templates.mkdir()
    for tpl in templates_dir.glob("*.j2"):
        (tmp_templates / tpl.name).write_text(
            tpl.read_text(encoding="utf-8"), encoding="utf-8"
        )

    (tmp_path / "docs" / "audio").mkdir(parents=True)
    (tmp_path / "docs" / "episodes").mkdir(parents=True)
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "episodes.json").write_text("[]", encoding="utf-8")

    return AppConfig(
        site=SiteConfig(
            title="Daily English Listening",
            description="Personal VOA Learning English listening practice.",
            github_username="tester",
            repository="voa-podcast",
            base_url="https://tester.github.io/voa-podcast",
            language="en-us",
        ),
        podcast=PodcastConfig(
            author="Private English Learner",
            explicit=False,
            block_public_directory=True,
        ),
        llm=LLMConfig(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            temperature=0.2,
            max_chars_per_request=4000,
        ),
        project_root=tmp_path,
    )


@pytest.fixture
def sample_episode() -> Episode:
    return Episode(
        id=1,
        guid="voa-podcast-001",
        title="AI Is Changing Education",
        slug="ai-is-changing-education",
        source="VOA Learning English",
        source_url="https://learningenglish.voanews.com/a/ai-education/123.html",
        published_at=datetime(2026, 8, 8, 10, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc),
        category="Science",
        english_text=(
            "Artificial intelligence is changing education.\n\n"
            "Many teachers are beginning to use AI tools."
        ),
        chinese_text=(
            "人工智能正在改变教育。\n\n"
            "许多老师开始使用人工智能工具。"
        ),
        audio_file="audio/001-ai-is-changing-education.mp3",
        audio_size=12345678,
        audio_type="audio/mpeg",
        audio_sha256="abc123",
        copyright_status="VOA_ORIGINAL",
    )
