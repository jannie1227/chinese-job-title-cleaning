"""Deterministic literal rule matching and overlap resolution."""

import re
from dataclasses import dataclass
from typing import Iterable

from chinese_job_title_cleaning._lexical.models import ReviewReason


_STANDARDIZED_PUNCTUATION = frozenset(",:;()[]/|·-，；（）【】、。！？：!?\"'")
_LATIN_TOKEN_CHARACTER = re.compile(r"[A-Za-z0-9+#.\-]")
_LATIN_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9+.#-]+\Z")


@dataclass(frozen=True, slots=True)
class MatchSpan:
    """One literal rule occurrence in the format-normalized source title."""

    start: int
    end: int
    rule_id: str
    priority: int
    canonical_value: str | None
    canonical_tag: str | None
    action: str | None
    source_kind: str
    match_type: str | None = None
    pattern: str | None = None


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Resolved rule channels and metadata for the cleaning pipeline.

    ``selected`` contains global overlap winners.  ``tag_spans`` resolves the
    extraction actions independently, so it can contain a span absent from
    ``selected`` when a competing mutator wins globally.  Task 6 must extract
    tags from ``tag_spans``; protected mutations only block deletion.
    """

    selected: tuple[MatchSpan, ...]
    protected: tuple[MatchSpan, ...]
    tag_spans: tuple[MatchSpan, ...]
    blocked_mutations: tuple[MatchSpan, ...]
    review_reasons: tuple[ReviewReason, ...]


def find_rule_spans(
    text: str, rules: Iterable[object], *, source_kind: str
) -> tuple[MatchSpan, ...]:
    """Find all literal occurrences for enabled rules without changing *text*."""
    spans: list[MatchSpan] = []
    for rule in rules:
        if not getattr(rule, "enabled", True):
            continue
        for start, end in _occurrences(text, rule.pattern, rule.match_type):
            spans.append(
                MatchSpan(
                    start=start,
                    end=end,
                    rule_id=rule.rule_id,
                    priority=rule.priority,
                    canonical_value=getattr(rule, "canonical_term", None),
                    canonical_tag=getattr(rule, "canonical_tag", None),
                    action=getattr(rule, "action", None),
                    source_kind=source_kind,
                    match_type=rule.match_type,
                    pattern=rule.pattern,
                )
            )
    return tuple(sorted(spans, key=lambda span: (span.start, span.end, span.rule_id)))


def resolve_matches(
    candidates: Iterable[MatchSpan], *, protected: Iterable[MatchSpan] = ()
) -> MatchResult:
    """Resolve global mutation and independent extraction channels deterministically.

    ``selected`` is the global non-overlapping result.  ``tag_spans`` is a
    separately ranked non-overlapping extraction channel for ``tag_only``,
    ``keep_and_tag``, and ``remove_and_tag`` actions.  It intentionally remains
    available when a protected deletion is blocked; consumers extract tags from
    ``tag_spans`` rather than inferring them from ``selected``.
    """
    candidate_spans = tuple(candidates)
    protected_spans = tuple(sorted(protected, key=_output_order))
    selected = tuple(sorted(_select_non_overlapping(candidate_spans), key=_output_order))
    tag_spans = tuple(
        sorted(
            _select_non_overlapping(
                span
                for span in candidate_spans
                if span.action in {"tag_only", "keep_and_tag", "remove_and_tag"}
            ),
            key=_output_order,
        )
    )
    blocked_mutations = _blocked_mutations(selected, protected_spans)
    has_conflict = _has_rule_conflict(candidate_spans)
    applicable_reasons = {
        ReviewReason.PROTECTED_OVERLAP: bool(blocked_mutations),
        ReviewReason.RULE_CONFLICT: has_conflict,
    }
    reasons = tuple(reason for reason in ReviewReason if applicable_reasons.get(reason, False))
    return MatchResult(selected, protected_spans, tag_spans, blocked_mutations, reasons)


def ordered_deduplicate(spans: Iterable[MatchSpan]) -> tuple[str, ...]:
    """Return canonical terms or tags once, ordered by their first source position."""
    values: list[str] = []
    seen: set[str] = set()
    for span in sorted(spans, key=_output_order):
        value = span.canonical_value if span.canonical_value is not None else span.canonical_tag
        if value is not None and value not in seen:
            seen.add(value)
            values.append(value)
    return tuple(values)


def replace_canonical_values(text: str, spans: Iterable[MatchSpan]) -> str:
    """Replace selected canonical values from right to left to avoid index drift."""
    ordered = tuple(sorted(spans, key=lambda item: (item.start, item.end, item.rule_id)))
    previous_end = 0
    for span in ordered:
        if span.start < 0 or span.end <= span.start or span.end > len(text):
            raise ValueError("invalid replacement span")
        if span.start < previous_end:
            raise ValueError("overlapping replacement spans")
        if span.canonical_value is None:
            raise ValueError("canonical value is required for replacement")
        previous_end = span.end
    result = text
    for span in reversed(ordered):
        result = result[: span.start] + span.canonical_value + result[span.end :]
    return result


def is_latin_token_pattern(pattern: str) -> bool:
    """Return whether *pattern* is one complete ASCII latin-token literal."""
    return _LATIN_TOKEN_PATTERN.fullmatch(pattern) is not None


def canonical_self_match_offsets(span: MatchSpan) -> tuple[tuple[int, int], ...]:
    """Find occurrences of a normalization rule within its canonical value."""
    if span.canonical_value is None or span.pattern is None or span.match_type is None:
        return ()
    return _occurrences(span.canonical_value, span.pattern, span.match_type)


def match_type_applies_at(
    text: str,
    start: int,
    end: int,
    match_type: str,
    *,
    title_start: int = 0,
    title_end: int | None = None,
) -> bool:
    """Return whether one literal occurrence matches within logical title bounds."""
    if title_end is None:
        title_end = len(text)
    if not 0 <= title_start <= start < end <= title_end <= len(text):
        return False
    if match_type == "exact":
        return start == title_start and end == title_end
    if match_type == "prefix":
        return start == title_start
    if match_type == "suffix":
        return end == title_end
    if match_type == "contains":
        return True
    if match_type == "delimited":
        return (start == title_start or _is_delimiter(text[start - 1])) and (
            end == title_end or _is_delimiter(text[end])
        )
    if match_type == "latin_token":
        return (start == title_start or not _LATIN_TOKEN_CHARACTER.fullmatch(text[start - 1])) and (
            end == title_end or not _LATIN_TOKEN_CHARACTER.fullmatch(text[end])
        )
    raise ValueError(f"unsupported match type: {match_type!r}")


def _occurrences(text: str, pattern: str, match_type: str) -> tuple[tuple[int, int], ...]:
    if not pattern:
        return ()
    if match_type == "exact":
        return ((0, len(text)),) if text == pattern else ()
    if match_type == "prefix":
        return ((0, len(pattern)),) if text.startswith(pattern) else ()
    if match_type == "suffix":
        start = len(text) - len(pattern)
        return ((start, len(text)),) if text.endswith(pattern) else ()
    if match_type == "contains":
        return tuple((start, start + len(pattern)) for start in _literal_starts(text, pattern))
    if match_type == "delimited":
        return tuple(
            (start, start + len(pattern))
            for start in _literal_starts(text, pattern)
            if match_type_applies_at(text, start, start + len(pattern), match_type)
        )
    if match_type == "latin_token":
        if not is_latin_token_pattern(pattern):
            raise ValueError("latin_token pattern must use only ASCII token characters")
        expression = re.compile(re.escape(pattern), flags=re.ASCII | re.IGNORECASE)
        return tuple(
            (match.start(), match.end())
            for match in expression.finditer(text)
            if match_type_applies_at(text, match.start(), match.end(), match_type)
        )
    raise ValueError(f"unsupported match type: {match_type!r}")


def _literal_starts(text: str, pattern: str) -> Iterable[int]:
    start = text.find(pattern)
    while start != -1:
        yield start
        start = text.find(pattern, start + len(pattern))


def _is_delimiter(character: str) -> bool:
    return character.isspace() or character in _STANDARDIZED_PUNCTUATION


def _select_non_overlapping(candidates: Iterable[MatchSpan]) -> tuple[MatchSpan, ...]:
    """Select spans for short titles and small validated rule sets.

    This direct overlap scan is intentionally simple and deterministic.  It is
    O(C²) in candidate count, which is appropriate for the bounded title/rule
    inputs here; revisit only with workload evidence.
    """
    selected: list[MatchSpan] = []
    for candidate in sorted(candidates, key=_selection_order):
        if not any(_overlaps(candidate, prior) for prior in selected):
            selected.append(candidate)
    return tuple(selected)


def _selection_order(span: MatchSpan) -> tuple[int, int, str, int, int]:
    return (-(span.end - span.start), span.priority, span.rule_id, span.start, span.end)


def _output_order(span: MatchSpan) -> tuple[int, str]:
    return (span.start, span.rule_id)


def _overlaps(left: MatchSpan, right: MatchSpan) -> bool:
    return left.start < right.end and right.start < left.end


def _blocked_mutations(
    selected: Iterable[MatchSpan], protected: Iterable[MatchSpan]
) -> tuple[MatchSpan, ...]:
    intervals = _merged_intervals(protected)
    blocked: list[MatchSpan] = []
    interval_index = 0
    for span in selected:
        if span.action not in {"remove", "remove_and_tag"}:
            continue
        while interval_index < len(intervals) and intervals[interval_index][1] <= span.start:
            interval_index += 1
        if interval_index < len(intervals) and intervals[interval_index][0] < span.end:
            blocked.append(span)
    return tuple(blocked)


def _merged_intervals(spans: Iterable[MatchSpan]) -> tuple[tuple[int, int], ...]:
    intervals: list[tuple[int, int]] = []
    for span in sorted(spans, key=lambda item: (item.start, item.end)):
        if intervals and span.start <= intervals[-1][1]:
            intervals[-1] = (intervals[-1][0], max(intervals[-1][1], span.end))
        else:
            intervals.append((span.start, span.end))
    return tuple(intervals)


def _has_rule_conflict(candidates: Iterable[MatchSpan]) -> bool:
    grouped: dict[tuple[int, int, int], list[MatchSpan]] = {}
    for span in candidates:
        grouped.setdefault((span.start, span.end, span.priority), []).append(span)
    for spans in grouped.values():
        values = {(span.action, span.canonical_value, span.canonical_tag) for span in spans}
        if len(values) > 1:
            return True
    return False
