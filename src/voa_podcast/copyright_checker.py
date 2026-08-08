"""Copyright checker for VOA articles.

Determines whether an article is VOA original content, sourced from a
third-party agency (AP / Reuters / AFP), or of unknown provenance.
"""

from __future__ import annotations

import logging
import re

from .models import CopyrightResult, CopyrightStatus, VOAArticle

logger = logging.getLogger(__name__)

THIRD_PARTY_PATTERNS = [
    (re.compile(r"\bAssociated Press\b", re.I), "Associated Press"),
    (re.compile(r"\bAgence France-Presse\b", re.I), "Agence France-Presse"),
    (re.compile(r"\bReuters\b", re.I), "Reuters"),
    (re.compile(r"\bAFP\b", re.I), "AFP"),
    (re.compile(r"\(AP\)", re.I), "AP"),
]


class CopyrightChecker:
    """Checks whether a VOA article may be redistributed as VOA original."""

    def check(self, article: VOAArticle) -> CopyrightResult:
        """Return a CopyrightResult for the given article."""
        haystack_parts = [
            article.copyright_source or "",
            article.author or "",
            article.english_text[:2000],
        ]
        haystack = "\n".join(haystack_parts)

        for pattern, label in THIRD_PARTY_PATTERNS:
            if pattern.search(haystack):
                logger.info("[COPYRIGHT] Third-party source detected: %s", label)
                return CopyrightResult(
                    status=CopyrightStatus.THIRD_PARTY,
                    matched_source=label,
                    reason=f"Article sourced from {label}.",
                )

        # VOA original markers.
        if self._is_voa_original(article, haystack):
            logger.info("[COPYRIGHT] VOA original confirmed.")
            return CopyrightResult(
                status=CopyrightStatus.VOA_ORIGINAL,
                matched_source="VOA",
                reason="No third-party markers found; treated as VOA original.",
            )

        logger.info("[COPYRIGHT] Copyright status unknown.")
        return CopyrightResult(
            status=CopyrightStatus.UNKNOWN,
            matched_source=None,
            reason="Unable to determine copyright source.",
        )

    @staticmethod
    def _is_voa_original(article: VOAArticle, haystack: str) -> bool:
        copyright_src = (article.copyright_source or "").lower()
        if "voa" in copyright_src or "voice of america" in copyright_src:
            return True
        # If nothing indicates a third party (word-boundary match, not
        # substring, to avoid false positives like "happen"/"paper") and we
        # have a valid article body, treat it as VOA original.
        if article.english_text and not any(
            pattern.search(haystack) for pattern, _ in THIRD_PARTY_PATTERNS
        ):
            return True
        return False
