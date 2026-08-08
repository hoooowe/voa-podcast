"""Podcast RSS 2.0 feed generator (Apple Podcasts compatible).

Generates docs/feed.xml with the itunes and content namespaces. Episode
descriptions embed the English original + Chinese translation inside a
``<content:encoded>`` CDATA block, with a "Read full transcript" link for
very long articles to avoid Apple Podcasts loading issues.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

from .audio_utils import format_duration, probe_duration
from .config import AppConfig
from .models import Episode

logger = logging.getLogger(__name__)

# Apple Podcasts may truncate very long descriptions; keep the inline
# transcript below this character budget and link out for the rest.
MAX_DESCRIPTION_CHARS = 4000


class RSSGenerator:
    """Generates the Podcast RSS feed from episodes."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def generate(self, episodes: list[Episode]) -> Path:
        """Write docs/feed.xml and return its path."""
        out = self._config.docs_dir / "feed.xml"
        out.parent.mkdir(parents=True, exist_ok=True)
        xml = self._render(episodes)
        out.write_text(xml, encoding="utf-8")
        logger.info("[RSS] Feed generated: %s", out)
        return out

    # ------------------------------------------------------------------ #
    def _render(self, episodes: list[Episode]) -> str:
        cfg = self._config
        site = cfg.site
        pc = cfg.podcast
        base = site.site_url

        channel_xml = self._render_channel(episodes)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" '
            'xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" '
            'xmlns:content="http://purl.org/rss/1.0/modules/content/" '
            'xmlns:podcast="https://podcastindex.org/namespace/1.0">\n'
            f"{channel_xml}\n"
            "</rss>\n"
        )

    def _render_channel(self, episodes: list[Episode]) -> str:
        cfg = self._config
        site = cfg.site
        pc = cfg.podcast
        base = site.site_url

        block = "Yes" if pc.block_public_directory else "No"
        explicit = "yes" if pc.explicit else "no"

        lines: list[str] = []
        lines.append("  <channel>")
        lines.append(f"    <title>{_escape(site.title)}</title>")
        lines.append(f"    <link>{_escape(base + '/')}</link>")
        lines.append(f"    <description>{_escape(site.description)}</description>")
        lines.append(f"    <language>{_escape(site.language)}</language>")
        lines.append(
            f'    <itunes:image href="{_attr(base + "/cover.jpg")}"/>'
        )
        lines.append(f"    <itunes:author>{_escape(pc.author)}</itunes:author>")
        lines.append(f"    <itunes:explicit>{explicit}</itunes:explicit>")
        lines.append("    <itunes:category text=\"Education\"/>")
        if pc.summary:
            lines.append(f"    <itunes:summary>{_escape(pc.summary)}</itunes:summary>")
        owner_parts = [f"<itunes:name>{_escape(pc.author)}</itunes:name>"]
        if pc.owner_email:
            owner_parts.append(f"<itunes:email>{_escape(pc.owner_email)}</itunes:email>")
        lines.append("    <itunes:owner>" + "".join(owner_parts) + "</itunes:owner>")
        lines.append(f"    <itunes:block>{block}</itunes:block>")
        lines.append(
            f'    <image><url>{_escape(base + "/cover.jpg")}</url>'
            f"<title>{_escape(site.title)}</title>"
            f"<link>{_escape(base + '/')}</link></image>"
        )

        # Episodes: newest first.
        sorted_episodes = sorted(episodes, key=lambda e: e.created_at, reverse=True)
        for ep in sorted_episodes:
            lines.append(self._render_item(ep))

        lines.append("  </channel>")
        return "\n".join(lines)

    def _render_item(self, ep: Episode) -> str:
        cfg = self._config
        base = cfg.site.site_url
        audio_url = f"{base}/{ep.audio_file.lstrip('/')}"
        page_url = f"{base}/episodes/{ep.slug}.html"

        pub_date = _rfc822_date(ep.published_at or ep.created_at)
        description_html = self._build_description(ep, page_url)
        summary_text = self._build_summary_text(ep)

        audio_path = cfg.docs_dir / ep.audio_file
        duration = format_duration(probe_duration(audio_path, ep.audio_size))

        lines: list[str] = []
        lines.append("    <item>")
        lines.append(f"      <title>{_escape(ep.title)}</title>")
        lines.append(f"      <link>{_escape(page_url)}</link>")
        lines.append(f"      <guid isPermaLink=\"false\">{_escape(ep.guid)}</guid>")
        lines.append(f"      <pubDate>{_escape(pub_date)}</pubDate>")
        lines.append(
            f'      <enclosure url="{_attr(audio_url)}" '
            f'length="{ep.audio_size}" type="{_attr(ep.audio_type)}"/>'
        )
        lines.append(f"      <description>{_escape(summary_text)}</description>")
        if duration:
            lines.append(f"      <itunes:duration>{_escape(duration)}</itunes:duration>")
        if ep.sentences:
            vtt_url = f"{base}/transcripts/{ep.slug}.vtt"
            lines.append(
                f'      <podcast:transcript url="{_attr(vtt_url)}" '
                f'type="text/vtt" language="en" rel="captions"/>'
            )
        lines.append(
            "      <content:encoded><![CDATA["
            + description_html
            + "]]></content:encoded>"
        )
        lines.append("    </item>")
        return "\n".join(lines)

    def _build_description(self, ep: Episode, page_url: str) -> str:
        """Build the HTML shown in Apple Podcasts episode description."""
        if ep.sentences:
            full = self._render_sentences_description(ep)
        else:
            full = self._render_paragraphs_description(ep)
        full += (
            "\n<hr/>"
            + f"\n<p>Source: {_escape(ep.source)}</p>"
            + f"\n<p>Original: <a href=\"{_attr(ep.source_url)}\">{_escape(ep.source_url)}</a></p>"
            + f"\n<p><a href=\"{_attr(page_url)}\">Open interactive transcript →</a></p>"
        )
        if len(full) <= MAX_DESCRIPTION_CHARS:
            return "\n" + full + "\n"

        # Truncate: keep as much as possible, then link out.
        truncated = full[: MAX_DESCRIPTION_CHARS - 200]
        last_p = truncated.rfind("</p>")
        if last_p > 0:
            truncated = truncated[: last_p + 4]
        truncated += (
            "\n<hr/>"
            f"\n<p><a href=\"{_attr(page_url)}\">Read full transcript →</a></p>"
        )
        return "\n" + truncated + "\n"

    def _render_sentences_description(self, ep: Episode) -> str:
        """Render bilingual sentence pairs (English + Chinese) per row."""
        parts = ["<h2>English &amp; 中文</h2>"]
        for s in ep.sentences:
            parts.append(
                f"<p><strong>{_escape(s.en)}</strong><br/>{_escape(s.zh)}</p>"
            )
        return "\n".join(parts)

    def _render_paragraphs_description(self, ep: Episode) -> str:
        """Render English and Chinese as separate paragraph blocks."""
        english_paras = _split_paragraphs(ep.english_text)
        chinese_paras = _split_paragraphs(ep.chinese_text)

        def render_block(title: str, paras: list[str]) -> str:
            block = [f"<h2>{title}</h2>"]
            for p in paras:
                block.append(f"<p>{_escape(p)}</p>")
            return "\n".join(block)

        return (
            render_block("English Original", english_paras)
            + "\n"
            + render_block("中文翻译", chinese_paras)
        )

    def _build_summary_text(self, ep: Episode) -> str:
        """Plain-text <description> fallback (short)."""
        snippet = ep.english_text[:200].replace("\n", " ")
        return (
            f"VOA Learning English - {ep.title}. "
            f"{snippet}... English original and Chinese translation in full notes."
        )


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _escape(text: str) -> str:
    return html.escape(text or "", quote=True)


def _attr(text: str) -> str:
    return html.escape(text or "", quote=True)


def _rfc822_date(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt, usegmt=True)
