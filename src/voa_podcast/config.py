"""Configuration loading from config.yaml and environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    max_chars_per_request: int = 4000


@dataclass
class SiteConfig:
    title: str
    description: str
    github_username: str
    repository: str
    base_url: str
    language: str = "en-us"

    @property
    def site_url(self) -> str:
        return self.base_url.rstrip("/")


@dataclass
class PodcastConfig:
    author: str
    explicit: bool = False
    block_public_directory: bool = True
    owner_email: str = ""
    summary: str = ""


@dataclass
class AppConfig:
    site: SiteConfig
    podcast: PodcastConfig
    llm: LLMConfig
    project_root: Path = PROJECT_ROOT
    copyright_strict: bool = False

    @property
    def docs_dir(self) -> Path:
        return self.project_root / "docs"

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def episodes_file(self) -> Path:
        return self.data_dir / "episodes.json"

    @property
    def templates_dir(self) -> Path:
        return self.project_root / "templates"

    @property
    def audio_dir(self) -> Path:
        return self.docs_dir / "audio"

    @property
    def episodes_html_dir(self) -> Path:
        return self.docs_dir / "episodes"

    @property
    def cache_dir(self) -> Path:
        return self.project_root / ".cache"


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load application configuration from config.yaml and .env."""
    load_dotenv(PROJECT_ROOT / ".env")

    if config_path is None:
        config_path = PROJECT_ROOT / "config.yaml"

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    site_raw = raw["site"]
    site = SiteConfig(
        title=site_raw["title"],
        description=site_raw["description"].strip(),
        github_username=site_raw["github_username"],
        repository=site_raw["repository"],
        base_url=site_raw["base_url"].strip(),
        language=site_raw.get("language", "en-us"),
    )

    podcast_raw = raw["podcast"]
    podcast = PodcastConfig(
        author=podcast_raw["author"],
        explicit=podcast_raw.get("explicit", False),
        block_public_directory=podcast_raw.get("block_public_directory", True),
        owner_email=podcast_raw.get("owner_email", ""),
        summary=podcast_raw.get("summary", ""),
    )

    translation_raw = raw.get("translation", {})
    max_chars = int(translation_raw.get("max_chars_per_request", 4000))
    temperature = float(translation_raw.get("temperature", 0.2))

    llm = LLMConfig(
        base_url=os.environ.get("LLM_BASE_URL", ""),
        api_key=os.environ.get("LLM_API_KEY", ""),
        model=os.environ.get("LLM_MODEL", ""),
        temperature=temperature,
        max_chars_per_request=max_chars,
    )

    copyright_raw = raw.get("copyright", {})
    copyright_strict = bool(copyright_raw.get("strict", False))

    return AppConfig(
        site=site,
        podcast=podcast,
        llm=llm,
        copyright_strict=copyright_strict,
    )
