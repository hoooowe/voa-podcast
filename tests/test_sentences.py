"""Tests for .lrc parsing, sentence translation, and sentence serialization."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from voa_podcast.content_parser import VOASEContentParser, parse_lrc
from voa_podcast.models import Episode, Sentence

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VOASE_URL = (
    "https://www.voase.cn/2025/03/2025-03-18-%5BHealth-and-Lifestyle%5D-"
    "Wilbur-and-Orville-Wright_-The-First-Airplane.html"
)


def _load_soup() -> BeautifulSoup:
    html = (FIXTURES_DIR / "voase_article.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "html.parser")


def _load_lrc() -> str:
    return (FIXTURES_DIR / "voase_article.lrc").read_text(encoding="utf-8")


# ---------------------------------------------------------------------- #
# parse_lrc
# ---------------------------------------------------------------------- #
def test_parse_lrc_skips_metadata_tags():
    sentences = parse_lrc(_load_lrc())
    # 5 timestamped lines, metadata header ignored.
    assert len(sentences) == 5
    assert all(isinstance(s[0], float) for s in sentences)


def test_parse_lrc_timestamps_correct():
    sentences = parse_lrc(_load_lrc())
    assert sentences[0] == (0.0, sentences[0][1])
    assert sentences[1][0] == 9.89
    assert sentences[2][0] == 17.72


def test_parse_lrc_ignores_empty_text_lines():
    lrc = "[ti:X]\n[00:00.00]First.\n[00:02.00]\n[00:03.00]Second.\n"
    sentences = parse_lrc(lrc)
    assert len(sentences) == 2
    assert sentences[0][1] == "First."
    assert sentences[1][1] == "Second."


# ---------------------------------------------------------------------- #
# VOASEContentParser with .lrc
# ---------------------------------------------------------------------- #
def test_voase_parse_with_lrc_builds_sentences():
    article = VOASEContentParser().parse(VOASE_URL, _load_soup(), lrc_text=_load_lrc())
    assert article.sentences is not None
    assert len(article.sentences) == 5
    assert article.sentences[0].start == 0.0
    assert article.sentences[1].start == 9.89
    assert article.sentences[1].en.startswith("They proved that flight")


def test_voase_parse_with_lrc_derives_english_text():
    article = VOASEContentParser().parse(VOASE_URL, _load_soup(), lrc_text=_load_lrc())
    # english_text is the sentences joined by blank lines.
    assert article.english_text.count("\n\n") == 4
    assert article.english_text.startswith("Wilbur and Orville Wright are")


def test_voase_parse_prefers_lrc_over_txt():
    txt = "Header line\n2025-03-18\n\nThis should NOT be used.\n"
    article = VOASEContentParser().parse(
        VOASE_URL, _load_soup(), txt_text=txt, lrc_text=_load_lrc()
    )
    assert article.sentences is not None
    assert "This should NOT be used." not in article.english_text


def test_voase_extract_lrc_url():
    url = VOASEContentParser().extract_lrc_url(VOASE_URL, _load_soup())
    assert url is not None
    assert url.endswith(".lrc")
    assert "%20" in url


# ---------------------------------------------------------------------- #
# Sentence / Episode serialization
# ---------------------------------------------------------------------- #
def test_sentence_round_trip():
    s = Sentence(start=12.5, en="Hello world.", zh="你好世界。")
    d = s.to_dict()
    assert d == {"start": 12.5, "en": "Hello world.", "zh": "你好世界。"}
    s2 = Sentence.from_dict(d)
    assert s2.start == 12.5
    assert s2.en == "Hello world."
    assert s2.zh == "你好世界。"


def test_episode_serializes_sentences():
    ep = Episode(
        id=1,
        guid="voa-podcast-001",
        title="T",
        slug="t",
        source="VOA",
        source_url="http://x",
        published_at=None,
        created_at=__import__("datetime").datetime(2025, 1, 1),
        category=None,
        english_text="en",
        chinese_text="zh",
        audio_file="audio/001-t.mp3",
        audio_size=100,
        audio_type="audio/mpeg",
        sentences=[Sentence(start=0.0, en="A", zh="甲"), Sentence(start=5.0, en="B", zh="乙")],
    )
    d = ep.to_dict()
    assert len(d["sentences"]) == 2
    ep2 = Episode.from_dict(d)
    assert len(ep2.sentences) == 2
    assert ep2.sentences[1].start == 5.0
    assert ep2.sentences[1].zh == "乙"


# ---------------------------------------------------------------------- #
# translate_sentences (mocked)
# ---------------------------------------------------------------------- #
def test_translate_sentences_alignment_and_cache(tmp_path):
    from voa_podcast.translator import OpenAICompatibleTranslator

    t = OpenAICompatibleTranslator(
        base_url="http://x", api_key="k", model="m", cache_dir=tmp_path
    )
    calls: list[list[str]] = []

    def fake(sentences):
        calls.append(list(sentences))
        return ["译" + str(i) for i in range(len(sentences))]

    t._call_api_sentences = fake  # type: ignore[assignment]
    ens = ["One.", "Two.", "Three."]
    zhs = t.translate_sentences(ens)
    assert zhs == ["译0", "译1", "译2"]
    assert len(calls) == 1


def test_translate_sentences_uses_cache(tmp_path):
    from voa_podcast.translator import OpenAICompatibleTranslator

    t = OpenAICompatibleTranslator(
        base_url="http://x", api_key="k", model="m", cache_dir=tmp_path
    )
    t._call_api_sentences = lambda s: ["X"] * len(s)  # type: ignore[assignment]
    t.translate_sentences(["Hello."])
    # Second call with same sentence must hit cache (no new API call).
    called = {"n": 0}
    orig = t._call_api_sentences
    def counter(s):
        called["n"] += 1
        return orig(s)
    t._call_api_sentences = counter  # type: ignore[assignment]
    zhs = t.translate_sentences(["Hello."])
    assert zhs == ["X"]
    assert called["n"] == 0


def test_translate_sentences_fallback_on_mismatch(tmp_path):
    from voa_podcast.translator import OpenAICompatibleTranslator

    t = OpenAICompatibleTranslator(
        base_url="http://x", api_key="k", model="m", cache_dir=tmp_path
    )
    # Batch returns wrong count -> triggers one-by-one fallback.
    t._call_api_sentences = lambda s: ["only one"]  # type: ignore[assignment]
    single_calls: list[str] = []
    def fake_single(s):
        single_calls.append(s)
        return "单译:" + s
    t._translate_single = fake_single  # type: ignore[assignment]
    zhs = t.translate_sentences(["A", "B"])
    assert zhs == ["单译:A", "单译:B"]
    assert len(single_calls) == 2
