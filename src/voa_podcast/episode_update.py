"""Stage a replacement episode and roll back a failed publication."""

import filecmp
from contextlib import ExitStack
from dataclasses import replace
from itertools import count
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory

from .config import AppConfig
from .episode_repository import EpisodeRepository, audio_filename
from .models import Episode
from .rss_generator import RSSGenerator
from .site_generator import SiteGenerator
from .transcript_generator import TranscriptGenerator


def publish_episode_update(
    config: AppConfig, original: Episode, updated: Episode, download: Path
) -> Episode:
    repo = EpisodeRepository(config.episodes_file)
    with repo.publication_lock():
        initial_data = config.episodes_file.read_bytes()
        episodes = repo.load_all()
    try:
        index = episodes.index(original)
    except ValueError:
        raise RuntimeError("The episode changed while preparing the update. Please retry.") from None
    if any(ep.id != original.id and ep.audio_sha256 == updated.audio_sha256 for ep in episodes):
        raise RuntimeError("Another episode already uses the replacement audio.")
    other_audio = {ep.audio_file for ep in episodes if ep.id != original.id}
    if original.audio_file in other_audio:
        # Historical records may share an enclosure. Give only the updated episode a new one.
        for suffix in count(2):
            name = audio_filename(original.id, f"{original.slug}-{suffix}")
            path = f"audio/{name}"
            if path not in other_audio and not (config.docs_dir / path).exists():
                updated = replace(updated, audio_file=path)
                break
    episodes[index] = updated

    with TemporaryDirectory(dir=config.project_root) as scratch:
        staged = replace(config, project_root=Path(scratch))
        copytree(config.templates_dir, staged.templates_dir)
        # The generators read other episodes' MP3s to determine their durations.
        borrowed_audio = set()
        for relative in other_audio:
            source = config.docs_dir / relative
            if not source.is_file():
                continue
            borrowed = staged.docs_dir / relative
            borrowed.parent.mkdir(parents=True, exist_ok=True)
            borrowed.hardlink_to(source)
            borrowed_audio.add(borrowed)
        audio = staged.docs_dir / updated.audio_file
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.hardlink_to(download)

        SiteGenerator(staged).generate(episodes)
        TranscriptGenerator(staged).generate_all(episodes)
        RSSGenerator(staged).generate(episodes)
        EpisodeRepository(staged.episodes_file).save_all(episodes)

        # Commit the episode record last. Keep the originals for rollback if a later rename fails.
        files: list[tuple[Path | None, Path]] = [
            (p, config.docs_dir / p.relative_to(staged.docs_dir))
            for p in staged.docs_dir.rglob("*") if p not in borrowed_audio and p.is_file()
        ]
        if original.sentences and not updated.sentences:
            for extension in (".vtt", ".en.vtt", ".srt"):
                old = config.docs_dir / "transcripts" / f"{original.slug}{extension}"
                if old.exists():
                    files.append((None, old))
        files.append((staged.episodes_file, config.episodes_file))
        with repo.publication_lock():
            if config.episodes_file.read_bytes() != initial_data:
                raise RuntimeError("Episode data changed during the update. Retry with the latest version.")
            _publish_files(files, Path(scratch))
    return updated


def _publish_files(files: list[tuple[Path | None, Path]], scratch: Path) -> None:
    with ExitStack() as rollback:
        for i, (staged, destination) in enumerate(files):
            destination.parent.mkdir(parents=True, exist_ok=True)
            backup = scratch / f"backup-{i}"
            if destination.exists():
                if staged is not None and filecmp.cmp(staged, destination, shallow=False):
                    continue
                backup.hardlink_to(destination)
            if staged is None:
                destination.unlink()
            else:
                staged.replace(destination)
            if backup.exists():
                rollback.callback(backup.replace, destination)
            else:
                rollback.callback(destination.unlink, missing_ok=True)
        rollback.pop_all()
