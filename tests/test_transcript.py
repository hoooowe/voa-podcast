"""Tests for VTT/SRT transcript generation."""

from __future__ import annotations

from voa_podcast.models import Episode, Sentence
from voa_podcast.transcript_generator import generate_srt, generate_vtt


def _episode() -> Episode:
    return Episode(
        id=1,
        guid="voa-podcast-001",
        title="Test",
        slug="test",
        source="VOA",
        source_url="http://x",
        published_at=None,
        created_at=__import__("datetime").datetime(2025, 1, 1),
        category=None,
        english_text="en",
        chinese_text="zh",
        audio_file="audio/001-test.mp3",
        audio_size=100,
        audio_type="audio/mpeg",
        sentences=[
            Sentence(start=0.0, en="Hello world.", zh="你好世界。"),
            Sentence(start=5.0, en="Goodbye.", zh="再见。"),
        ],
    )


def test_vtt_header_and_cues():
    vtt = generate_vtt(_episode(), duration=10.0)
    assert vtt.startswith("WEBVTT\n")
    # Two cues, each with a timestamp line.
    assert "00:00:00.000 --> 00:00:05.000" in vtt
    assert "00:00:05.000 --> 00:00:10.000" in vtt


def test_vtt_includes_bilingual_lines():
    vtt = generate_vtt(_episode(), duration=10.0)
    assert "Hello world." in vtt
    assert "你好世界。" in vtt
    assert "Goodbye." in vtt
    assert "再见。" in vtt


def test_srt_uses_comma_decimal_and_indices():
    srt = generate_srt(_episode(), duration=10.0)
    assert srt.startswith("1\n")
    assert "00:00:00,000 --> 00:00:05,000" in srt
    assert "2\n00:00:05,000 --> 00:00:10,000" in srt


def test_last_cue_end_falls_back_when_duration_unknown():
    # No duration -> last cue end = last start + 8s tail.
    vtt = generate_vtt(_episode(), duration=0.0)
    assert "00:00:05.000 --> 00:00:13.000" in vtt
