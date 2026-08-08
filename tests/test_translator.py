"""Tests for translation batching and SHA256 caching (no network)."""

from __future__ import annotations

import hashlib
import json

from voa_podcast.translator import OpenAICompatibleTranslator


def test_cache_hit_skips_api(tmp_path):
    text = "Artificial intelligence is changing education."
    cache_key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cache_file = tmp_path / f"{cache_key}.json"
    cache_file.write_text(
        json.dumps({"sha256": cache_key, "chinese_text": "人工智能正在改变教育。"}),
        encoding="utf-8",
    )

    translator = OpenAICompatibleTranslator(
        base_url="https://api.example.com/v1",
        api_key="should-not-be-used",
        model="test-model",
        cache_dir=tmp_path,
    )
    result = translator.translate(text)
    assert result == "人工智能正在改变教育。"


def test_cache_miss_calls_fake_api(tmp_path, monkeypatch):
    text = "Hello world."

    translator = OpenAICompatibleTranslator(
        base_url="https://api.example.com/v1",
        api_key="test-key",
        model="test-model",
        cache_dir=tmp_path,
        max_chars_per_request=4000,
    )

    calls: list[str] = []

    def fake_call_api(self, payload_text):  # noqa: ANN001
        calls.append(payload_text)
        return "你好，世界。"

    monkeypatch.setattr(OpenAICompatibleTranslator, "_call_api", fake_call_api)

    result = translator.translate(text)
    assert result == "你好，世界。"
    assert len(calls) == 1

    # Second call should hit cache, no new API call.
    result2 = translator.translate(text)
    assert result2 == "你好，世界。"
    assert len(calls) == 1


def test_batching_splits_long_text(tmp_path, monkeypatch):
    # 10 paragraphs, each ~50 chars -> with max_chars=120 they batch.
    paragraphs = [f"Paragraph number {i} with some extra words here." for i in range(10)]
    text = "\n\n".join(paragraphs)

    translator = OpenAICompatibleTranslator(
        base_url="https://api.example.com/v1",
        api_key="test-key",
        model="test-model",
        cache_dir=tmp_path,
        max_chars_per_request=120,
    )

    batches = translator._build_batches(paragraphs)
    assert len(batches) > 1
    # Each batch must respect the limit (with paragraph separator overhead).
    for batch in batches:
        assert len(batch) <= 120 + 60  # allow single oversized paragraph


def test_batching_preserves_order(tmp_path, monkeypatch):
    paragraphs = ["One.", "Two.", "Three.", "Four.", "Five."]
    text = "\n\n".join(paragraphs)

    translator = OpenAICompatibleTranslator(
        base_url="https://api.example.com/v1",
        api_key="test-key",
        model="test-model",
        cache_dir=tmp_path,
        max_chars_per_request=10,
    )

    received: list[str] = []

    def fake_call_api(self, payload_text):  # noqa: ANN001
        received.append(payload_text)
        return payload_text.replace("One", "一").replace("Two", "二").replace(
            "Three", "三"
        ).replace("Four", "四").replace("Five", "五")

    monkeypatch.setattr(OpenAICompatibleTranslator, "_call_api", fake_call_api)

    result = translator.translate(text)
    # Translated paragraphs rejoined in original order.
    assert "一" in result
    assert "五" in result
    assert result.index("一") < result.index("五")
