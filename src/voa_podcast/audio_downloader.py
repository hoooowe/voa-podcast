"""Downloads VOA original English MP3 audio and computes metadata.

Also defines the AudioStorage abstraction so the storage backend (GitHub
Pages vs. external object storage) can be swapped without touching the
core podcast pipeline.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
from pathlib import Path
from typing import Protocol

import requests

from .models import AudioMetadata

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120
CHUNK_SIZE = 8192
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class AudioDownloadError(Exception):
    """Raised when audio download fails."""


class AudioDownloader:
    """Downloads an MP3 file and records size, MIME type, and SHA256."""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    def download(self, audio_url: str, destination: Path) -> AudioMetadata:
        """Download ``audio_url`` to ``destination`` and return metadata."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        logger.info("[AUDIO] Downloading from %s", audio_url)

        try:
            resp = self._session.get(audio_url, timeout=DEFAULT_TIMEOUT, stream=True)
        except requests.RequestException as exc:
            raise AudioDownloadError(f"Failed to download audio: {exc}") from exc

        if resp.status_code != 200:
            raise AudioDownloadError(
                f"Audio download returned HTTP {resp.status_code}"
            )

        sha256 = hashlib.sha256()
        total = 0
        with destination.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    sha256.update(chunk)
                    total += len(chunk)

        mime_type = (
            resp.headers.get("Content-Type", "").split(";")[0].strip()
            or mimetypes.guess_type(str(destination))[0]
            or "audio/mpeg"
        )
        # Normalize common variants; MP3 is always audio/mpeg for podcasts.
        if "mpeg" in mime_type or "mp3" in mime_type:
            mime_type = "audio/mpeg"

        size_mb = total / (1024 * 1024)
        logger.info("[AUDIO] Downloaded %.1f MB", size_mb)

        return AudioMetadata(
            local_path=destination,
            file_size=total,
            mime_type=mime_type,
            sha256=sha256.hexdigest(),
        )


class AudioStorage(Protocol):
    """Abstract audio storage backend.

    Saves a local audio file and returns its public URL.
    """

    def save(self, local_file: Path) -> str:
        ...


class GitHubPagesAudioStorage:
    """Stores audio under docs/audio/ and returns a GitHub Pages URL."""

    def __init__(self, audio_dir: Path, base_url: str) -> None:
        self._audio_dir = audio_dir
        self._base_url = base_url.rstrip("/")

    def save(self, local_file: Path) -> str:
        """Copy/move the file into docs/audio/ and return its public URL.

        The file is expected to already be inside ``audio_dir`` (downloaded
        there directly). We return its public URL based on ``base_url``.
        """
        rel = local_file.name
        return f"{self._base_url}/audio/{rel}"
