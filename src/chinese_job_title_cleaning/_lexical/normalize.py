"""Shared, lossless text normalization primitives."""

import re
import unicodedata
from typing import TYPE_CHECKING, Callable

from chinese_job_title_cleaning._lexical.models import CleanAction
from chinese_job_title_cleaning._lexical.title_structure import (
    MAX_TEXT_CODEPOINTS,
    canonicalize_separators,
    normalize_entities,
)


if TYPE_CHECKING:
    from chinese_job_title_cleaning._lexical.matcher import MatchSpan


_MAX_NORMALIZATION_PASSES = 10_000
_MAX_NORMALIZED_TITLE_LENGTH = MAX_TEXT_CODEPOINTS
_WHITESPACE = re.compile(r"\s+")
# Slashes and pipes can be structural (for example in URLs and alternatives),
# so only comma/semicolon runs are unambiguously decorative here.
_REPEATED_DISPLAY_PUNCTUATION = re.compile(r"([,;])\1+")
_REPEATED_IDEOGRAPHIC_COMMA = re.compile(r"、{2,}")
_HAN_AMPERSAND = re.compile(
    r"(?<=[\u3400-\u4dbf\u4e00-\u9fff])\s*&\s*(?=[\u3400-\u4dbf\u4e00-\u9fff])"
)
_SEPARATOR_SPACING = re.compile(r"\s*([()\[\]/|])\s*")


def normalize_base(value: str) -> str:
    """Apply the common Unicode and whitespace normalization contract."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value).strip())


def normalize_title_format(value: str) -> str:
    """Normalize display punctuation without changing title meaning or terms.

    This intentionally performs no term replacement or deletion.  Only bracket,
    separator, connector, hyphen, and repeated display punctuation variants are
    standardized; technical punctuation such as ``+``, ``#``, and ``.`` is
    untouched.
    """
    normalized = normalize_base(canonicalize_separators(value))
    normalized = _REPEATED_DISPLAY_PUNCTUATION.sub(r"\1", normalized)
    normalized = _REPEATED_IDEOGRAPHIC_COMMA.sub("/", normalized)
    normalized = _HAN_AMPERSAND.sub("/", normalized)
    return _SEPARATOR_SPACING.sub(r"\1", normalized)


def normalize_title(value: str, rule_set: object) -> str:
    """Format a title and apply its enabled term-normalization rules.

    The matcher import stays local: :mod:`chinese_job_title_cleaning._lexical.rules` imports this
    module for ``normalize_base``, so importing it at module load time would
    form a cycle.
    """
    normalized, _ = normalize_title_with_audit(value, rule_set)
    return normalized


def normalize_title_with_audit(value: str, rule_set: object) -> tuple[str, bool]:
    """Normalize one title and report whether a whitelisted entity was decoded."""
    entity_result = normalize_entities(value)
    return (
        _normalize_decoded_title(entity_result.text, rule_set),
        CleanAction.DECODE_HTML_ENTITY in entity_result.actions,
    )


def _normalize_decoded_title(value: str, rule_set: object) -> str:
    """Normalize a title after its single HTML-entity substitution pass."""
    from chinese_job_title_cleaning._lexical.matcher import (
        canonical_self_match_offsets,
        find_rule_spans,
        replace_canonical_values,
        resolve_matches,
    )

    current = normalize_title_format(value)
    if len(current) > _MAX_NORMALIZED_TITLE_LENGTH:
        raise ValueError("normalized title exceeds safety limit")
    enabled_rules = tuple(rule for rule in rule_set.normalization if rule.enabled)
    seen = {current}
    maximum_intermediate_length = len(current)
    rule_count = max(1, len(enabled_rules))
    passes = 0
    while True:
        candidates = find_rule_spans(current, enabled_rules, source_kind="normalization")
        selected = tuple(
            span
            for span in resolve_matches(candidates).selected
            if not _canonical_value_is_aligned(current, span, canonical_self_match_offsets)
        )
        updated = replace_canonical_values(current, selected)
        passes += 1
        if updated == current:
            return current
        if updated in seen:
            raise ValueError("normalization does not converge: rule cycle detected")
        if len(updated) > _MAX_NORMALIZED_TITLE_LENGTH:
            raise ValueError("normalized title exceeds safety limit")
        seen.add(updated)
        maximum_intermediate_length = max(maximum_intermediate_length, len(updated))
        maximum_iterations = min(
            _MAX_NORMALIZATION_PASSES, maximum_intermediate_length * rule_count + 1
        )
        if passes >= maximum_iterations:
            raise ValueError("normalization does not converge within the safety bound")
        current = updated


def _canonical_value_is_aligned(
    text: str,
    span: "MatchSpan",
    self_match_offsets: Callable[["MatchSpan"], tuple[tuple[int, int], ...]],
) -> bool:
    canonical_value = span.canonical_value
    if canonical_value is None or span.pattern is None or span.match_type is None:
        return False
    for offset, _ in self_match_offsets(span):
        canonical_start = span.start - offset
        canonical_end = canonical_start + len(canonical_value)
        if canonical_start >= 0 and canonical_end <= len(text):
            if text[canonical_start:canonical_end] == canonical_value:
                return True
    return False
