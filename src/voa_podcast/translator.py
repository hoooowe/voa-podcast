"""LLM translation with an abstract provider and SHA256 result caching.

The translator batches long articles by paragraph to respect token limits,
and caches translations keyed by SHA256(english_text) so re-runs do not
incur duplicate LLM cost.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Protocol

import requests

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an English-to-Chinese translator for language learners.

Translate the following VOA Learning English article
into natural Simplified Chinese.

Requirements:

1. Preserve paragraph structure.
2. Do not summarize.
3. Do not omit information.
4. Do not add explanations.
5. Keep names, organizations and technical terms accurate.
6. Produce only Simplified Chinese translation."""

DEFAULT_TIMEOUT = 120

SENTENCE_SYSTEM_PROMPT = """You are an English-to-Chinese translator for language learners.

You will receive a JSON array of English sentences. Translate EACH sentence
into natural Simplified Chinese and return a JSON array of translations, in the
SAME ORDER and with the SAME COUNT as the input.

Rules:
- Output ONLY the JSON array. No markdown fences, no commentary.
- One translation per input sentence.
- Keep names, organizations and technical terms accurate.
- Do not add explanations or merge/split sentences."""


class TranslationError(Exception):
    """Raised when translation fails."""


class TranslationProvider(Protocol):
    """Abstract translation provider interface."""

    def translate(self, text: str) -> str:
        ...


class OpenAICompatibleTranslator:
    """Translator backed by an OpenAI-compatible /chat/completions API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        max_chars_per_request: int = 4000,
        cache_dir: Path | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_chars = max_chars_per_request
        self._cache_dir = cache_dir
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def translate(self, text: str) -> str:
        """Translate English text to Simplified Chinese, using cache."""
        if not text.strip():
            return ""

        cached = self._load_cache(text)
        if cached is not None:
            logger.info("[TRANSLATE] Cache hit, skipping LLM call.")
            return cached

        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        batches = self._build_batches(paragraphs)
        logger.info("[TRANSLATE] Translating %d paragraphs in %d batches...",
                    len(paragraphs), len(batches))

        translated_batches: list[str] = []
        for batch in batches:
            result = self._call_api(batch)
            translated_batches.append(result)

        full_translation = "\n\n".join(translated_batches)
        self._save_cache(text, full_translation)
        return full_translation

    def translate_sentences(self, sentences: list[str]) -> list[str]:
        """Translate a list of English sentences to Chinese, 1:1 aligned.

        Uses per-sentence SHA256 caching and batches uncached sentences into
        JSON-array requests. If a batch returns a mismatched number of
        translations, falls back to translating those sentences one by one.
        """
        results: list[str | None] = [None] * len(sentences)
        todo: list[tuple[int, str]] = []
        for i, s in enumerate(sentences):
            if not s.strip():
                results[i] = ""
                continue
            cached = self._load_cache(s)
            if cached is not None:
                results[i] = cached
            else:
                todo.append((i, s))

        if not todo:
            logger.info("[TRANSLATE] All %d sentences cached.", len(sentences))
            return [r or "" for r in results]

        batches = self._build_sentence_batches(todo)
        logger.info(
            "[TRANSLATE] Translating %d sentences in %d batches...",
            len(todo), len(batches),
        )
        for batch in batches:
            ens = [s for _, s in batch]
            try:
                zhs = self._call_api_sentences(ens)
            except TranslationError as exc:
                logger.warning("[TRANSLATE] Batch JSON failed (%s); translating one-by-one.", exc)
                zhs = [self._translate_single(s) for s in ens]
            if len(zhs) != len(ens):
                logger.warning(
                    "[TRANSLATE] Batch length mismatch (%d vs %d); translating one-by-one.",
                    len(zhs), len(ens),
                )
                zhs = [self._translate_single(s) for s in ens]
            for (idx, s), zh in zip(batch, zhs):
                results[idx] = zh
                self._save_cache(s, zh)
        return [r or "" for r in results]

    def _build_sentence_batches(
        self, todo: list[tuple[int, str]]
    ) -> list[list[tuple[int, str]]]:
        batches: list[list[tuple[int, str]]] = []
        current: list[tuple[int, str]] = []
        current_len = 0
        for item in todo:
            s_len = len(item[1])
            if current and current_len + s_len + 8 > self._max_chars:
                batches.append(current)
                current = [item]
                current_len = s_len
            else:
                current.append(item)
                current_len += s_len + 8
        if current:
            batches.append(current)
        return batches

    def _call_api_sentences(self, sentences: list[str]) -> list[str]:
        """Translate a batch of sentences via a JSON-array request."""
        if not self._api_key:
            raise TranslationError(
                "LLM_API_KEY is not configured. Set it in .env or repository secrets."
            )
        if not self._model:
            raise TranslationError("LLM_MODEL is not configured.")

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": [
                {"role": "system", "content": SENTENCE_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(sentences, ensure_ascii=False)},
            ],
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            raise TranslationError(f"LLM API request failed: {exc}") from exc
        if resp.status_code != 200:
            raise TranslationError(
                f"LLM API returned HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise TranslationError(f"Unexpected LLM API response: {exc}") from exc

        cleaned = _strip_code_fences(content)
        try:
            arr = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise TranslationError(f"LLM did not return valid JSON: {exc}") from exc
        if not isinstance(arr, list):
            raise TranslationError("LLM JSON was not an array.")
        return [str(x) for x in arr]

    def _translate_single(self, sentence: str) -> str:
        """Translate one sentence as plain text (fallback for bad batches)."""
        cached = self._load_cache(sentence)
        if cached is not None:
            return cached
        result = self._call_api(sentence)
        self._save_cache(sentence, result)
        return result

    # ------------------------------------------------------------------ #
    # Batching
    # ------------------------------------------------------------------ #
    def _build_batches(self, paragraphs: list[str]) -> list[str]:
        batches: list[str] = []
        current: list[str] = []
        current_len = 0
        for para in paragraphs:
            para_len = len(para)
            if current and current_len + para_len + 4 > self._max_chars:
                batches.append("\n\n".join(current))
                current = [para]
                current_len = para_len
            else:
                current.append(para)
                current_len += para_len + 4
        if current:
            batches.append("\n\n".join(current))
        return batches

    # ------------------------------------------------------------------ #
    # API call
    # ------------------------------------------------------------------ #
    def _call_api(self, text: str) -> str:
        if not self._api_key:
            raise TranslationError(
                "LLM_API_KEY is not configured. Set it in .env or repository secrets."
            )
        if not self._model:
            raise TranslationError("LLM_MODEL is not configured.")

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            raise TranslationError(f"LLM API request failed: {exc}") from exc

        if resp.status_code != 200:
            raise TranslationError(
                f"LLM API returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise TranslationError(f"Unexpected LLM API response: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Cache
    # ------------------------------------------------------------------ #
    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _cache_path(self, text: str) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / f"{self._cache_key(text)}.json"

    def _load_cache(self, text: str) -> str | None:
        path = self._cache_path(text)
        if path is None or not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("chinese_text")
        except (json.JSONDecodeError, OSError):
            return None

    def _save_cache(self, text: str, translation: str) -> None:
        path = self._cache_path(text)
        if path is None:
            return
        try:
            path.write_text(
                json.dumps(
                    {"sha256": self._cache_key(text), "chinese_text": translation},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("[TRANSLATE] Failed to write cache: %s", exc)


_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*\n?|\n?```\s*$")


def _strip_code_fences(content: str) -> str:
    """Remove surrounding markdown code fences from an LLM response."""
    stripped = content.strip()
    if stripped.startswith("```"):
        # Drop the opening fence (with optional language) and trailing fence.
        stripped = _CODE_FENCE_RE.sub("", stripped).strip()
    return stripped
