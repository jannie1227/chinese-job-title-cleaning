"""Deterministic, rule-driven primitives for canonical job-title text."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from chinese_job_title_cleaning._lexical.models import CleanAction, ReviewReason


MAX_TEXT_CODEPOINTS = 10_000

_WHITESPACE = re.compile(r"\s+")
_ENTITY = re.compile(r"&#0*32;|&#[xX]0*20;|&amp;|&lt;|&gt;|&quot;|&apos;")
_RESIDUAL_ENTITY = re.compile(r"&(?:#[xX][0-9A-Fa-f]+|#[0-9]+|[A-Za-z][A-Za-z0-9]+);")
_ENTITY_REPLACEMENTS = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
}
_SEPARATOR_TRANSLATION = str.maketrans(
    {
        "／": "/",
        "∕": "/",
        "⁄": "/",
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
        "﹣": "-",
        "－": "-",
        "｜": "|",
        "¦": "|",
        "・": "·",
        "•": "·",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "［": "[",
        "］": "]",
        "〔": "[",
        "〕": "]",
        "〖": "[",
        "〗": "]",
        "〈": "[",
        "〉": "]",
        "「": "[",
        "」": "]",
        "『": "[",
        "』": "]",
    }
)
_UNPROTECTED_PUNCTUATION = str.maketrans({character: " " for character in "-/|_·,;:!?+#."})
_ALLOWED_ASCII_SYMBOLS = frozenset("/-|_,;:!?+#.")
_BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}"}
_CLOSING_BRACKETS = frozenset(_BRACKET_PAIRS.values())
_PRIVATE_USE_RANGES = (
    (0xE000, 0xF8FF),
    (0xF0000, 0xFFFFD),
    (0x100000, 0x10FFFD),
)


@dataclass(frozen=True, slots=True)
class ReviewEvidence:
    """One deduplicated fragment that caused a conservative review reason."""

    reason: ReviewReason
    value: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class TextStructureResult:
    """Canonical text plus ordered public audit evidence."""

    text: str
    actions: tuple[CleanAction, ...]
    review_reasons: tuple[ReviewReason, ...]
    review_evidence: tuple[ReviewEvidence, ...]

    @property
    def reasons(self) -> tuple[ReviewReason, ...]:
        """Return the stable short name for review reasons."""
        return self.review_reasons


@dataclass(frozen=True, slots=True)
class TechnicalSpan:
    """One caller-authorized technical token in canonical source offsets."""

    start: int
    end: int
    source: str
    canonical: str


@dataclass(frozen=True, slots=True)
class ProtectedTechnicalText:
    """Masked technical spans and the data needed to restore them exactly once."""

    text: str
    marker: str
    replacements: tuple[str, ...]
    spans: tuple[TechnicalSpan, ...]


@dataclass(frozen=True, slots=True)
class BracketStripResult:
    """Bracket deletion result with an explicit fail-closed matching signal."""

    text: str
    removed: tuple[str, ...]
    actions: tuple[CleanAction, ...]
    review_reasons: tuple[ReviewReason, ...]
    review_evidence: tuple[ReviewEvidence, ...]
    eligible_for_matching: bool

    @property
    def reasons(self) -> tuple[ReviewReason, ...]:
        """Return the stable short name for review reasons."""
        return self.review_reasons


def normalize_entities(value: str) -> TextStructureResult:
    """Apply NFKC and one allowlisted HTML-entity replacement pass."""
    normalized = _nfkc_checked(value)
    decoded, decoded_any = _replace_entities_once(normalized)
    text = _collapse_whitespace(decoded)
    evidence = _residual_entity_evidence(text)
    actions = _ordered_actions(
        normalize=normalized != value or text != decoded,
        decoded=decoded_any,
    )
    reasons = (ReviewReason.UNKNOWN_HTML_ENTITY,) if evidence else ()
    return TextStructureResult(text, actions, reasons, evidence)


def canonicalize_separators(value: str) -> str:
    """Apply NFKC and only the closed separator/bracket character mapping."""
    return _nfkc_checked(value).translate(_SEPARATOR_TRANSLATION)


def normalize_title_structure(value: str) -> TextStructureResult:
    """Canonicalize basic title structure without deleting semantic content."""
    normalized = _nfkc_checked(value)
    mapped = normalized.translate(_SEPARATOR_TRANSLATION)
    decoded, decoded_any = _replace_entities_once(mapped)
    text = _collapse_whitespace(decoded)
    evidence = _deduplicate_evidence(
        (*_residual_entity_evidence(text), *_unknown_symbol_evidence(text))
    )
    reason_set = {item.reason for item in evidence}
    reasons = tuple(reason for reason in ReviewReason if reason in reason_set)
    actions = _ordered_actions(
        normalize=normalized != value or mapped != normalized or text != decoded,
        decoded=decoded_any,
    )
    return TextStructureResult(text, actions, reasons, evidence)


def strip_bracket_blocks(value: str) -> BracketStripResult:
    """Delete balanced outermost bracket blocks or preserve the canonical title."""
    canonical = normalize_title_structure(value)
    intervals, invalid_index = _validated_outermost_bracket_intervals(canonical.text)
    if invalid_index is not None:
        bracket_evidence = ReviewEvidence(
            ReviewReason.UNBALANCED_BRACKET,
            canonical.text[invalid_index],
            invalid_index,
            invalid_index + 1,
        )
        evidence = _deduplicate_evidence((*canonical.review_evidence, bracket_evidence))
        reason_set = {item.reason for item in evidence}
        reasons = tuple(reason for reason in ReviewReason if reason in reason_set)
        return BracketStripResult(
            canonical.text,
            (),
            canonical.actions,
            reasons,
            evidence,
            False,
        )

    if not intervals:
        return BracketStripResult(
            canonical.text,
            (),
            canonical.actions,
            canonical.review_reasons,
            canonical.review_evidence,
            True,
        )

    pieces: list[str] = []
    removed: list[str] = []
    cursor = 0
    for start, end in intervals:
        pieces.append(canonical.text[cursor:start])
        removed.append(canonical.text[start:end])
        cursor = end
    pieces.append(canonical.text[cursor:])
    text = _collapse_whitespace("".join(pieces))
    actions = _merge_actions(canonical.actions, CleanAction.REMOVE_BRACKET_CONTENT)
    return BracketStripResult(
        text,
        tuple(removed),
        actions,
        canonical.review_reasons,
        canonical.review_evidence,
        True,
    )


def find_technical_spans(text: str, technical_rules: Iterable[object]) -> tuple[TechnicalSpan, ...]:
    """Find a deterministic non-overlapping set of caller-supplied technical terms."""
    _check_length(text)
    candidates: list[TechnicalSpan] = []
    for pattern, canonical in _technical_terms(technical_rules):
        expression = re.compile(re.escape(pattern), flags=re.ASCII | re.IGNORECASE)
        candidates.extend(
            TechnicalSpan(match.start(), match.end(), match.group(), canonical)
            for match in expression.finditer(text)
        )
    selected: list[TechnicalSpan] = []
    for candidate in sorted(
        candidates,
        key=lambda span: (
            span.start,
            -(span.end - span.start),
            span.canonical.encode("utf-8"),
            span.source.encode("utf-8"),
        ),
    ):
        if not selected or candidate.start >= selected[-1].end:
            selected.append(candidate)
    return tuple(selected)


def protect_technical_spans(text: str, technical_rules: Iterable[object]) -> ProtectedTechnicalText:
    """Replace technical spans with one deterministic collision-free PUA marker."""
    spans = find_technical_spans(text, technical_rules)
    marker = _unused_private_use_marker(text + "".join(span.canonical for span in spans))
    pieces: list[str] = []
    cursor = 0
    for span in spans:
        pieces.extend((text[cursor : span.start], marker))
        cursor = span.end
    pieces.append(text[cursor:])
    return ProtectedTechnicalText(
        "".join(pieces),
        marker,
        tuple(span.canonical for span in spans),
        spans,
    )


def restore_technical_spans(protected: ProtectedTechnicalText, text: str | None = None) -> str:
    """Restore each protected marker with its canonical technical value."""
    value = protected.text if text is None else text
    parts = value.split(protected.marker)
    if len(parts) - 1 != len(protected.replacements):
        raise ValueError("technical protection marker count changed")
    output = [parts[0]]
    for replacement, suffix in zip(protected.replacements, parts[1:], strict=True):
        output.extend((replacement, suffix))
    return "".join(output)


def cleanup_unprotected_punctuation(value: str, technical_rules: Iterable[object]) -> str:
    """Turn punctuation outside supplied technical spans into token-separating spaces."""
    canonical = _collapse_whitespace(canonicalize_separators(value))
    protected = protect_technical_spans(canonical, technical_rules)
    cleaned = _collapse_whitespace(protected.text.translate(_UNPROTECTED_PUNCTUATION))
    return _collapse_whitespace(restore_technical_spans(protected, cleaned))


def _nfkc_checked(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    _check_length(normalized)
    return normalized


def _check_length(value: str) -> None:
    if len(value) > MAX_TEXT_CODEPOINTS:
        raise ValueError("normalized title exceeds safety limit of 10,000 code points")


def _replace_entities_once(value: str) -> tuple[str, bool]:
    decoded_any = False

    def replacement(match: re.Match[str]) -> str:
        nonlocal decoded_any
        decoded_any = True
        entity = match.group()
        return _ENTITY_REPLACEMENTS.get(entity, " ")

    return _ENTITY.sub(replacement, value), decoded_any


def _collapse_whitespace(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _residual_entity_evidence(value: str) -> tuple[ReviewEvidence, ...]:
    return _deduplicate_evidence(
        ReviewEvidence(ReviewReason.UNKNOWN_HTML_ENTITY, match.group(), match.start(), match.end())
        for match in _RESIDUAL_ENTITY.finditer(value)
    )


def _unknown_symbol_evidence(value: str) -> tuple[ReviewEvidence, ...]:
    return _deduplicate_evidence(
        ReviewEvidence(ReviewReason.UNKNOWN_SYMBOL, character, index, index + 1)
        for index, character in enumerate(value)
        if unicodedata.category(character).startswith("S")
        and character not in _ALLOWED_ASCII_SYMBOLS
    )


def _deduplicate_evidence(evidence: Iterable[ReviewEvidence]) -> tuple[ReviewEvidence, ...]:
    output: list[ReviewEvidence] = []
    seen: set[tuple[ReviewReason, str]] = set()
    for item in sorted(evidence, key=lambda item: (item.start, item.end, item.reason.value)):
        key = (item.reason, item.value)
        if key not in seen:
            seen.add(key)
            output.append(item)
    return tuple(output)


def _validated_outermost_bracket_intervals(
    value: str,
) -> tuple[tuple[tuple[int, int], ...], int | None]:
    stack: list[tuple[str, int]] = []
    intervals: list[tuple[int, int]] = []
    outer_start = 0
    for index, character in enumerate(value):
        if character in _BRACKET_PAIRS:
            if not stack:
                outer_start = index
            stack.append((character, index))
            continue
        if character not in _CLOSING_BRACKETS:
            continue
        if not stack or _BRACKET_PAIRS[stack[-1][0]] != character:
            return (), index
        stack.pop()
        if not stack:
            intervals.append((outer_start, index + 1))
    if stack:
        return (), stack[0][1]
    return tuple(intervals), None


def _merge_actions(
    existing: tuple[CleanAction, ...], *additional: CleanAction
) -> tuple[CleanAction, ...]:
    selected = {*existing, *additional}
    return tuple(action for action in CleanAction if action in selected)


def _ordered_actions(*, normalize: bool, decoded: bool) -> tuple[CleanAction, ...]:
    selected = {
        action
        for action, enabled in (
            (CleanAction.NORMALIZE_TITLE, normalize),
            (CleanAction.DECODE_HTML_ENTITY, decoded),
        )
        if enabled
    }
    return tuple(action for action in CleanAction if action in selected)


def _technical_terms(technical_rules: Iterable[object]) -> tuple[tuple[str, str], ...]:
    values: set[tuple[str, str]] = set()
    for rule in technical_rules:
        if not getattr(rule, "enabled", True):
            continue
        pattern = getattr(rule, "pattern", None)
        canonical = getattr(rule, "canonical_tag", None)
        if canonical is None:
            canonical = getattr(rule, "canonical_term", None)
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("technical rule pattern must be a nonempty string")
        if not isinstance(canonical, str) or not canonical:
            raise ValueError("technical rule canonical value must be a nonempty string")
        values.add((pattern, canonical))
    return tuple(
        sorted(values, key=lambda item: (item[0].encode("utf-8"), item[1].encode("utf-8")))
    )


def _unused_private_use_marker(value: str) -> str:
    occupied = set(value)
    for start, end in _PRIVATE_USE_RANGES:
        for code_point in range(start, end + 1):
            marker = chr(code_point)
            if marker not in occupied:
                return marker
    raise RuntimeError("no private-use technical marker is available")
