"""Conservative, auditable cleaning of one normalized job title."""

import re
from dataclasses import dataclass, field, replace

from chinese_job_title_cleaning._lexical.matcher import (
    MatchSpan,
    find_rule_spans,
    match_type_applies_at,
    ordered_deduplicate,
    resolve_matches,
)
from chinese_job_title_cleaning._lexical.models import CleanAction, CleanStatus, ReviewReason
from chinese_job_title_cleaning._lexical.normalize import normalize_title_with_audit
from chinese_job_title_cleaning._lexical.rules import RuleSet


_TITLE_CONTENT = re.compile(r"[0-9A-Za-z\u3400-\u4dbf\u4e00-\u9fff]")
_HAN_OR_LATIN = re.compile(r"[A-Za-z\u3400-\u4dbf\u4e00-\u9fff]")
_WHITESPACE = re.compile(r"\s+")
_LOCAL_SEPARATOR_CLASS = r"[,;/|·:、。!?-]"
_PRIVATE_USE_RANGES = (
    (0xE000, 0xF8FF),
    (0xF0000, 0xFFFFD),
    (0x100000, 0x10FFFD),
)


@dataclass(frozen=True, slots=True)
class TitleCleanResult:
    """Title audit fields plus internal normalized pre-deletion evidence."""

    clean_title: str
    removed_terms: tuple[str, ...]
    location_tag: tuple[str, ...]
    employment_tag: tuple[str, ...]
    clean_actions: tuple[CleanAction, ...]
    review_reason: tuple[ReviewReason, ...]
    clean_status: CleanStatus
    normalized_pre_deletion_title: str = field(default="", compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class _TitleCleanRound:
    result: TitleCleanResult
    mutation_spans: tuple[MatchSpan, ...]
    removed_spans: tuple[MatchSpan, ...]
    location_tag_spans: tuple[MatchSpan, ...]
    employment_tag_spans: tuple[MatchSpan, ...]
    unsafe_empty_result: bool


def clean_title(raw_title: str, rule_set: RuleSet) -> TitleCleanResult:
    """Clean one title without inferring anything beyond the declared rules."""
    normalized_title, decoded_html_entity = normalize_title_with_audit(raw_title, rule_set)
    if not normalized_title:
        raise ValueError("raw title must normalize to a nonblank value")

    action_set: set[CleanAction] = set()
    reason_set: set[ReviewReason] = set()
    removed_term_events: list[tuple[int, str, str]] = []
    location_tag_events: list[tuple[int, str, str]] = []
    employment_tag_events: list[tuple[int, str, str]] = []
    if normalized_title != raw_title:
        action_set.add(CleanAction.NORMALIZE_TITLE)
    if decoded_html_entity:
        action_set.add(CleanAction.DECODE_HTML_ENTITY)

    clean_value = normalized_title
    source_positions = list(range(len(normalized_title)))
    for _ in range(len(normalized_title) + 1):
        round_details = _clean_normalized_title_once(clean_value, rule_set)
        round_result = round_details.result
        removed_term_events.extend(
            _source_value_events(round_details.removed_spans, source_positions)
        )
        location_tag_events.extend(
            _source_value_events(round_details.location_tag_spans, source_positions)
        )
        employment_tag_events.extend(
            _source_value_events(round_details.employment_tag_spans, source_positions)
        )
        action_set.update(round_result.clean_actions)
        reason_set.update(round_result.review_reason)
        if round_result.clean_title == clean_value:
            if clean_value != normalized_title and round_details.unsafe_empty_result:
                clean_value = normalized_title
                removed_term_events.clear()
                action_set.difference_update(
                    {
                        CleanAction.REMOVE_RECRUITMENT_PHRASE,
                        CleanAction.CLEANUP_PUNCTUATION,
                    }
                )
            break
        if len(round_result.clean_title) >= len(clean_value):
            raise RuntimeError("each deletion round must strictly shorten the title")
        source_positions = _subsequence_source_positions(
            clean_value,
            round_result.clean_title,
            source_positions,
            round_details.mutation_spans,
        )
        clean_value = round_result.clean_title
    else:  # pragma: no cover - strict shrink makes exhaustion unreachable
        raise RuntimeError("deletion fixed point exceeded its safe bound")

    removed_terms = _ordered_source_values(removed_term_events)
    location_tag = _ordered_source_values(location_tag_events)
    employment_tag = _ordered_source_values(employment_tag_events)
    clean_actions = tuple(action for action in CleanAction if action in action_set)
    review_reason = tuple(reason for reason in ReviewReason if reason in reason_set)
    if review_reason:
        clean_status = CleanStatus.REVIEW
    elif clean_value != raw_title or removed_terms or location_tag or employment_tag:
        clean_status = CleanStatus.CLEANED
    else:
        clean_status = CleanStatus.UNCHANGED

    return TitleCleanResult(
        clean_value,
        removed_terms,
        location_tag,
        employment_tag,
        clean_actions,
        review_reason,
        clean_status,
        normalized_pre_deletion_title=normalized_title,
    )


def _clean_normalized_title_once(normalized_title: str, rule_set: RuleSet) -> _TitleCleanRound:
    action_set: set[CleanAction] = set()
    protected = find_rule_spans(normalized_title, rule_set.protected, source_kind="protected")
    candidates = (
        *find_rule_spans(normalized_title, rule_set.recruitment, source_kind="recruitment"),
        *find_rule_spans(normalized_title, rule_set.locations, source_kind="location"),
        *find_rule_spans(normalized_title, rule_set.employment, source_kind="employment"),
    )
    matches = resolve_matches(candidates, protected=protected)

    location_tag_spans = [span for span in matches.tag_spans if span.source_kind == "location"]
    employment_tag_spans = [span for span in matches.tag_spans if span.source_kind == "employment"]

    reason_set = set(matches.review_reasons)
    active_review_rules = tuple(
        rule
        for rule in rule_set.review
        if rule.review_reason != ReviewReason.TITLE_INDUSTRY_MISMATCH
        if find_rule_spans(normalized_title, (rule,), source_kind="review")
    )
    reason_set.update(ReviewReason(rule.review_reason) for rule in active_review_rules)
    active_review_barriers = frozenset(("review", rule.rule_id) for rule in active_review_rules)

    blocked = set(matches.blocked_mutations)
    eligible: list[MatchSpan] = []
    for span in matches.selected:
        if (
            span in blocked
            or span.source_kind != "recruitment"
            or span.action not in {"remove", "remove_and_tag"}
        ):
            continue
        passive_tags = tuple(
            tag_span
            for tag_span in matches.tag_spans
            if tag_span.action in {"tag_only", "keep_and_tag"}
            and span.start <= tag_span.start
            and tag_span.end <= span.end
        )
        ignored_barriers = active_review_barriers | frozenset(
            (tag_span.source_kind, tag_span.rule_id) for tag_span in passive_tags
        )
        coalesced, skipped_tag_spans = _coalesce_boundary_repetitions(
            normalized_title,
            span,
            rule_set,
            ignored_barriers=ignored_barriers,
            passive_tag_spans=passive_tags,
        )
        eligible.append(coalesced)
        location_tag_spans.extend(
            tag_span for tag_span in skipped_tag_spans if tag_span.source_kind == "location"
        )
        employment_tag_spans.extend(
            tag_span for tag_span in skipped_tag_spans if tag_span.source_kind == "employment"
        )
    location_tag = ordered_deduplicate(location_tag_spans)
    employment_tag = ordered_deduplicate(employment_tag_spans)
    if location_tag:
        action_set.add(CleanAction.EXTRACT_LOCATION)
    if employment_tag:
        action_set.add(CleanAction.EXTRACT_EMPLOYMENT)
    proposed: list[MatchSpan] = []
    unsafe_empty_result = False
    if eligible and not _has_title_content(_delete_spans(normalized_title, eligible)):
        unsafe_empty_result = True
        reason_set.add(ReviewReason.UNSAFE_EMPTY_RESULT)
    else:
        proposed = eligible

    removed_terms: tuple[str, ...] = ()
    if proposed:
        clean_value, cleaned_punctuation = _cleanup_after_deletions(
            normalized_title,
            proposed,
            repair_deletion_caused_trailing_slash=True,
        )
        if not clean_value or not _has_title_content(clean_value):
            unsafe_empty_result = True
            reason_set.add(ReviewReason.UNSAFE_EMPTY_RESULT)
            clean_value = normalized_title
            proposed = []
        else:
            removed_terms = ordered_deduplicate(
                span for span in proposed if span.source_kind == "recruitment"
            )
            if removed_terms:
                action_set.add(CleanAction.REMOVE_RECRUITMENT_PHRASE)
            if cleaned_punctuation:
                action_set.add(CleanAction.CLEANUP_PUNCTUATION)
    else:
        clean_value = normalized_title

    clean_actions = tuple(action for action in CleanAction if action in action_set)
    review_reason = tuple(reason for reason in ReviewReason if reason in reason_set)
    if review_reason:
        clean_status = CleanStatus.REVIEW
    elif clean_value != normalized_title or removed_terms or location_tag or employment_tag:
        clean_status = CleanStatus.CLEANED
    else:
        clean_status = CleanStatus.UNCHANGED

    return _TitleCleanRound(
        TitleCleanResult(
            clean_value,
            removed_terms,
            location_tag,
            employment_tag,
            clean_actions,
            review_reason,
            clean_status,
        ),
        tuple(proposed),
        tuple(span for span in proposed if span.source_kind == "recruitment"),
        tuple(location_tag_spans),
        tuple(employment_tag_spans),
        unsafe_empty_result,
    )


def _source_value_events(
    spans: tuple[MatchSpan, ...], source_positions: list[int]
) -> tuple[tuple[int, str, str], ...]:
    events: list[tuple[int, str, str]] = []
    for span in spans:
        value = span.canonical_value if span.canonical_value is not None else span.canonical_tag
        if value is not None:
            events.append((source_positions[span.start], span.rule_id, value))
    return tuple(events)


def _ordered_source_values(events: list[tuple[int, str, str]]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for _, _, value in sorted(events):
        if value not in seen:
            seen.add(value)
            values.append(value)
    return tuple(values)


def _subsequence_source_positions(
    before: str,
    after: str,
    source_positions: list[int],
    removed_spans: tuple[MatchSpan, ...],
) -> list[int]:
    removed_indexes = {index for span in removed_spans for index in range(span.start, span.end)}
    surviving_source = [
        (character, source_positions[index])
        for index, character in enumerate(before)
        if index not in removed_indexes
    ]
    remaining_positions: list[int] = []
    search_start = 0
    for character in after:
        while search_start < len(surviving_source) and (
            surviving_source[search_start][0] != character
        ):
            search_start += 1
        if search_start == len(surviving_source):
            raise RuntimeError("deletion result must be a subsequence of its source title")
        remaining_positions.append(surviving_source[search_start][1])
        search_start += 1
    return remaining_positions


def _coalesce_boundary_repetitions(
    text: str,
    span: MatchSpan,
    rule_set: RuleSet,
    *,
    ignored_barriers: frozenset[tuple[str, str]],
    passive_tag_spans: tuple[MatchSpan, ...],
) -> tuple[MatchSpan, tuple[MatchSpan, ...]]:
    pattern = span.pattern
    if (
        span.match_type not in {"prefix", "suffix"}
        or not pattern
        or re.search(_LOCAL_SEPARATOR_CLASS, pattern)
    ):
        return span, ()

    start = span.start
    end = span.end
    width = len(pattern)
    if span.match_type == "prefix":
        while text.startswith(pattern, end):
            end += width
    else:
        while start >= width and text[start - width : start] == pattern:
            start -= width
    if (start, end) == (span.start, span.end):
        return span, ()
    boundary = _nearest_intermediate_rule_boundary(
        text,
        span,
        start,
        end,
        width,
        rule_set,
        ignored_barriers=ignored_barriers,
    )
    if boundary is not None:
        if span.match_type == "prefix":
            end = boundary
        else:
            start = boundary
    coalesced = replace(span, start=start, end=end)
    skipped_tag_spans: list[MatchSpan] = []
    if span.match_type == "suffix" and start < span.start:
        for tag_span in passive_tag_spans:
            relative_start = tag_span.start - span.start
            relative_end = tag_span.end - span.start
            for unit_start in range(start, span.start, width):
                candidate_start = unit_start + relative_start
                candidate_end = unit_start + relative_end
                if match_type_applies_at(
                    text,
                    candidate_start,
                    candidate_end,
                    tag_span.match_type,
                    title_end=unit_start + width,
                ):
                    skipped_tag_spans.append(
                        replace(tag_span, start=candidate_start, end=candidate_end)
                    )
                    break
    return coalesced, tuple(skipped_tag_spans)


def _nearest_intermediate_rule_boundary(
    text: str,
    selected: MatchSpan,
    run_start: int,
    run_end: int,
    repetition_width: int,
    rule_set: RuleSet,
    *,
    ignored_barriers: frozenset[tuple[str, str]],
) -> int | None:
    rules = (
        *(("recruitment", rule) for rule in rule_set.recruitment),
        *(("protected", rule) for rule in rule_set.protected),
        *(("review", rule) for rule in rule_set.review),
        *(("location", rule) for rule in rule_set.locations),
        *(("employment", rule) for rule in rule_set.employment),
    )
    nearest: int | None = None
    for source_kind, rule in rules:
        if (
            not getattr(rule, "enabled", True)
            or (source_kind, rule.rule_id) == (selected.source_kind, selected.rule_id)
            or (source_kind, rule.rule_id) in ignored_barriers
            or not rule.pattern
        ):
            continue
        if selected.match_type == "prefix":
            if rule.match_type not in {
                "prefix",
                "suffix",
                "exact",
                "delimited",
                "latin_token",
            }:
                continue
            occurrence = text.find(rule.pattern, selected.end)
            while 0 <= occurrence < run_end:
                occurrence_end = occurrence + len(rule.pattern)
                boundary = (
                    selected.end
                    + ((occurrence - selected.end) // repetition_width) * repetition_width
                )
                if match_type_applies_at(
                    text,
                    occurrence,
                    occurrence_end,
                    rule.match_type,
                    title_start=boundary,
                ):
                    if nearest is None or boundary < nearest:
                        nearest = boundary
                    break
                occurrence = text.find(rule.pattern, occurrence + 1)
        else:
            if rule.match_type not in {
                "prefix",
                "suffix",
                "exact",
                "delimited",
                "latin_token",
            }:
                continue
            occurrence = text.rfind(rule.pattern, 0, selected.start)
            while occurrence >= 0:
                occurrence_end = occurrence + len(rule.pattern)
                boundary = (
                    selected.start
                    - ((selected.start - occurrence_end) // repetition_width) * repetition_width
                )
                if run_start < occurrence_end <= selected.start and match_type_applies_at(
                    text,
                    occurrence,
                    occurrence_end,
                    rule.match_type,
                    title_end=boundary,
                ):
                    if nearest is None or boundary > nearest:
                        nearest = boundary
                    break
                occurrence = text.rfind(rule.pattern, 0, occurrence)
    return nearest


def _location_removal_is_safe(text: str, span: MatchSpan) -> bool:
    remainder = text[: span.start] + text[span.end :]
    return _has_two_title_letters(remainder)


def _has_two_title_letters(value: str) -> bool:
    return len(_HAN_OR_LATIN.findall(value)) >= 2


def has_occupational_content(value: str) -> bool:
    """Return whether *value* retains a letter, digit, or Han character."""
    return _TITLE_CONTENT.search(value) is not None


_has_title_content = has_occupational_content


def _delete_spans(text: str, spans: list[MatchSpan]) -> str:
    result = text
    for span in sorted(spans, key=lambda item: (item.start, item.end), reverse=True):
        result = result[: span.start] + result[span.end :]
    return result


def _cleanup_after_deletions(
    value: str,
    spans: list[MatchSpan],
    *,
    repair_deletion_caused_trailing_slash: bool = False,
) -> tuple[str, bool]:
    marker = _unused_private_use_marker(value)
    marked_parts: list[str] = []
    previous_end = 0
    for span in sorted(spans, key=lambda item: (item.start, item.end)):
        marked_parts.extend((value[previous_end : span.start], marker))
        previous_end = span.end
    marked_parts.append(value[previous_end:])
    value = "".join(marked_parts)

    value, repaired_bracket_slash = _repair_bracket_slashes(
        value,
        marker,
        repair_deletion_caused_trailing_slash=repair_deletion_caused_trailing_slash,
    )
    value = _collapse_adjacent_deletion_markers(value, marker)

    escaped_marker = re.escape(marker)
    marked_run = rf"(?:{escaped_marker}\s*)+"
    separator_run = rf"(?:{_LOCAL_SEPARATOR_CLASS}\s*)+"
    cleaned_punctuation = repaired_bracket_slash
    previous = None
    while value != previous:
        previous = value
        value, count = re.subn(
            rf"{marked_run}{_LOCAL_SEPARATOR_CLASS}\s*{marked_run}", marker, value
        )
        cleaned_punctuation |= count > 0
        value, count = re.subn(rf"\(\s*{marked_run}\)", marker, value)
        cleaned_punctuation |= count > 0
        value, count = re.subn(rf"\[\s*{marked_run}\]", marker, value)
        cleaned_punctuation |= count > 0
        value, count = re.subn(rf"^{separator_run}{marked_run}", marker, value)
        cleaned_punctuation |= count > 0
        value, count = re.subn(rf"{marked_run}{separator_run}$", marker, value)
        cleaned_punctuation |= count > 0
        value, count = re.subn(
            rf"({_LOCAL_SEPARATOR_CLASS})\s*{marked_run}{_LOCAL_SEPARATOR_CLASS}",
            r"\1",
            value,
        )
        cleaned_punctuation |= count > 0
        value, count = re.subn(rf"^{marked_run}{separator_run}", marker, value)
        cleaned_punctuation |= count > 0
        value, count = re.subn(rf"{separator_run}{marked_run}$", marker, value)
        cleaned_punctuation |= count > 0
    value = value.replace(marker, "")
    return _WHITESPACE.sub(" ", value).strip(), cleaned_punctuation


def _collapse_adjacent_deletion_markers(value: str, marker: str) -> str:
    collapsed: list[str] = []
    previous_was_marker = False
    for character in value:
        is_marker = character == marker
        if not (is_marker and previous_was_marker):
            collapsed.append(character)
        previous_was_marker = is_marker
    return "".join(collapsed)


def _unused_private_use_marker(value: str) -> str:
    source_characters = set(value)
    for first_codepoint, last_codepoint in _PRIVATE_USE_RANGES:
        for codepoint in range(first_codepoint, last_codepoint + 1):
            candidate = chr(codepoint)
            if candidate not in source_characters:
                return candidate
    raise RuntimeError("no private-use deletion marker is available")


def _repair_bracket_slashes(
    value: str,
    marker: str,
    *,
    repair_deletion_caused_trailing_slash: bool,
) -> tuple[str, bool]:
    matching_opener = {")": "(", "]": "["}
    stack: list[tuple[str, int, list[int]]] = []
    component_repairs: list[int] = []
    eligible_repairs: set[int] = set()
    marker_width = len(marker)
    index = 0
    while index < len(value):
        if value.startswith(marker, index):
            if stack:
                stack[-1][2].append(index)
            index += marker_width
            continue

        character = value[index]
        if character in "([":
            if not stack:
                component_repairs = []
            stack.append((character, index, []))
        elif character in ")]":
            if not stack or stack[-1][0] != matching_opener[character]:
                if stack:
                    stack.clear()
                    component_repairs = []
            else:
                _, opening_index, marker_indexes = stack.pop()
                component_repairs.extend(
                    _block_slash_repairs(
                        value,
                        opening_index,
                        index,
                        marker_indexes,
                        marker_width,
                        repair_deletion_caused_trailing_slash,
                    )
                )
                if not stack:
                    eligible_repairs.update(component_repairs)
                    component_repairs = []
        index += 1

    if not eligible_repairs:
        return value, False
    return (
        "".join(
            character
            for character_index, character in enumerate(value)
            if character_index not in eligible_repairs
        ),
        True,
    )


def _block_slash_repairs(
    value: str,
    opening_index: int,
    closing_index: int,
    marker_indexes: list[int],
    marker_width: int,
    repair_deletion_caused_trailing_slash: bool,
) -> tuple[int, ...]:
    content_start = opening_index + 1
    marker_runs = _contiguous_marker_runs(marker_indexes, marker_width)
    deletion_cluster_repairs = _trailing_deletion_cluster_slashes(
        value,
        content_start,
        closing_index,
        marker_runs,
        enabled=repair_deletion_caused_trailing_slash,
    )
    if deletion_cluster_repairs:
        return deletion_cluster_repairs

    if len(marker_runs) == 1:
        marker_start, marker_end = marker_runs[0]
        if (
            marker_start == content_start
            and marker_end + 1 < closing_index
            and value[marker_end] == "/"
        ):
            return (marker_end,)
        if (
            marker_end == closing_index
            and marker_start - 1 > content_start
            and value[marker_start - 1] == "/"
        ):
            return (marker_start - 1,)
        if (
            marker_start - 1 > content_start
            and marker_end + 1 < closing_index
            and value[marker_start - 1] == "/"
            and value[marker_end] == "/"
        ):
            return (marker_end,)
        return ()

    if len(marker_runs) == 2:
        first_marker_start, first_marker_end = marker_runs[0]
        second_marker_start, second_marker_end = marker_runs[1]
        first_slash = first_marker_end
        second_slash = second_marker_start - 1
        if (
            first_marker_start == content_start
            and second_marker_end == closing_index
            and first_slash + 1 < second_slash
            and value[first_slash] == "/"
            and value[second_slash] == "/"
        ):
            return (first_slash, second_slash)
    return ()


def _trailing_deletion_cluster_slashes(
    value: str,
    content_start: int,
    closing_index: int,
    marker_runs: tuple[tuple[int, int], ...],
    *,
    enabled: bool,
) -> tuple[int, ...]:
    if not enabled or not marker_runs:
        return ()

    first_marker_start = marker_runs[0][0]
    final_marker_end = marker_runs[-1][1]
    if (
        first_marker_start - 1 <= content_start
        or not _has_title_content(value[content_start : first_marker_start - 1])
        or value[first_marker_start - 1] != "/"
        or final_marker_end + 1 != closing_index
        or value[final_marker_end] != "/"
    ):
        return ()

    repairs = [first_marker_start - 1]
    for (_, marker_end), (next_marker_start, _) in zip(marker_runs, marker_runs[1:]):
        if next_marker_start != marker_end + 1 or value[marker_end] != "/":
            return ()
        repairs.append(marker_end)
    repairs.append(final_marker_end)
    return tuple(repairs)


def _contiguous_marker_runs(
    marker_indexes: list[int], marker_width: int
) -> tuple[tuple[int, int], ...]:
    runs: list[tuple[int, int]] = []
    for marker_start in marker_indexes:
        marker_end = marker_start + marker_width
        if runs and marker_start == runs[-1][1]:
            runs[-1] = (runs[-1][0], marker_end)
        else:
            runs.append((marker_start, marker_end))
    return tuple(runs)
