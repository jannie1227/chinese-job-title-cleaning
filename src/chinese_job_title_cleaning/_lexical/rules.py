"""Validated, versioned rule-file loading for the job-title cleaner.

Rule CSV cells are single-line values; embedded line feeds are invalid.
"""

import csv
import hashlib
import io
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from chinese_job_title_cleaning._lexical.matcher import is_latin_token_pattern
from chinese_job_title_cleaning._lexical.models import CategoryType, ReviewReason
from chinese_job_title_cleaning._lexical.normalize import normalize_base


TEXT_RULE_HEADER = (
    "rule_id",
    "pattern",
    "canonical_tag",
    "match_type",
    "priority",
    "action",
    "enabled",
    "rationale",
)
RECRUITMENT_HEADER = TEXT_RULE_HEADER
LOCATION_HEADER = TEXT_RULE_HEADER
EMPLOYMENT_HEADER = TEXT_RULE_HEADER
PROTECTED_HEADER = TEXT_RULE_HEADER
BENEFIT_HEADER = TEXT_RULE_HEADER
COMPANY_HEADER = TEXT_RULE_HEADER
JOB_CODE_HEADER = TEXT_RULE_HEADER
SENIORITY_HEADER = TEXT_RULE_HEADER
TECHNICAL_HEADER = TEXT_RULE_HEADER
LOCATION_PROTECTED_HEADER = TEXT_RULE_HEADER
INSUFFICIENT_HEADER = TEXT_RULE_HEADER
NORMALIZATION_HEADER = (
    "rule_id",
    "pattern",
    "canonical_term",
    "match_type",
    "priority",
    "enabled",
    "rationale",
)
CATEGORY_HEADER = (
    "rule_id",
    "field",
    "source_value",
    "clean_value",
    "category_type",
    "priority",
    "enabled",
    "rationale",
)
REVIEW_HEADER = (
    "rule_id",
    "title_pattern",
    "industry_values",
    "match_type",
    "review_reason",
    "enabled",
    "rationale",
)
SOURCE_QUALITY_HEADER = (
    "rule_id",
    "category",
    "term",
    "match_mode",
    "action",
    "enabled",
    "rationale",
)
REQUIREMENT_HEADER = (
    "rule_id",
    "pattern_type",
    "literals",
    "units",
    "priority",
    "action",
    "enabled",
    "rationale",
)
OCCUPATION_MARKER_HEADER = (
    "marker_id",
    "pattern",
    "match_type",
    "action",
    "enabled",
    "rationale",
)
MULTI_OCCUPATION_CONTEXT_HEADER = (
    "rule_id",
    "source_prefix",
    "target_marker",
    "candidate_prefix",
    "enabled",
    "rationale",
)
CLASSIFICATION_CONTAMINATION_HEADER = (
    "rule_id",
    "field",
    "pattern",
    "match_type",
    "action",
    "enabled",
    "rationale",
)

RULE_FILENAMES = (
    "recruitment_phrases.csv",
    "location_terms.csv",
    "employment_terms.csv",
    "protected_terms.csv",
    "normalization_terms.csv",
    "category_mappings.csv",
    "review_patterns.csv",
    "source_quality_terms.csv",
    "benefit_terms.csv",
    "requirement_patterns.csv",
    "company_terms.csv",
    "job_code_patterns.csv",
    "seniority_terms.csv",
    "technical_tokens.csv",
    "location_protected_terms.csv",
    "insufficient_titles.csv",
    "occupation_markers.csv",
    "classification_contamination_terms.csv",
    "multi_occupation_context_rules.csv",
)
_RULE_FILE_HEADERS = {
    "recruitment_phrases.csv": RECRUITMENT_HEADER,
    "location_terms.csv": LOCATION_HEADER,
    "employment_terms.csv": EMPLOYMENT_HEADER,
    "protected_terms.csv": PROTECTED_HEADER,
    "normalization_terms.csv": NORMALIZATION_HEADER,
    "category_mappings.csv": CATEGORY_HEADER,
    "review_patterns.csv": REVIEW_HEADER,
    "source_quality_terms.csv": SOURCE_QUALITY_HEADER,
    "benefit_terms.csv": BENEFIT_HEADER,
    "requirement_patterns.csv": REQUIREMENT_HEADER,
    "company_terms.csv": COMPANY_HEADER,
    "job_code_patterns.csv": JOB_CODE_HEADER,
    "seniority_terms.csv": SENIORITY_HEADER,
    "technical_tokens.csv": TECHNICAL_HEADER,
    "location_protected_terms.csv": LOCATION_PROTECTED_HEADER,
    "insufficient_titles.csv": INSUFFICIENT_HEADER,
    "occupation_markers.csv": OCCUPATION_MARKER_HEADER,
    "classification_contamination_terms.csv": CLASSIFICATION_CONTAMINATION_HEADER,
    "multi_occupation_context_rules.csv": MULTI_OCCUPATION_CONTEXT_HEADER,
}
RULE_FILE_HEADERS: Mapping[str, tuple[str, ...]] = MappingProxyType(_RULE_FILE_HEADERS)
_SNAPSHOT_FILENAMES = tuple(
    sorted(("rule_versions.json", *RULE_FILENAMES), key=lambda name: name.encode("utf-8"))
)

_TEXT_MATCH_TYPES = frozenset(("exact", "prefix", "suffix", "contains"))
_TEXT_RULE_ACTIONS = MappingProxyType(
    {
        "location_terms.csv": "remove_and_tag",
        "recruitment_phrases.csv": "remove",
        "employment_terms.csv": "keep_and_tag",
        "protected_terms.csv": "protect",
        "benefit_terms.csv": "remove",
        "company_terms.csv": "remove_and_tag",
        "job_code_patterns.csv": "remove_and_tag",
        "seniority_terms.csv": "keep_and_tag",
        "technical_tokens.csv": "protect",
        "location_protected_terms.csv": "protect",
        "insufficient_titles.csv": "flag_only",
    }
)
_TEXT_RULE_GROUPS = MappingProxyType(
    {
        "recruitment_phrases.csv": "recruitment",
        "location_terms.csv": "locations",
        "employment_terms.csv": "employment",
        "protected_terms.csv": "protected",
        "benefit_terms.csv": "benefits",
        "company_terms.csv": "companies",
        "job_code_patterns.csv": "job_codes",
        "seniority_terms.csv": "seniority",
        "technical_tokens.csv": "technical",
        "location_protected_terms.csv": "location_protected",
        "insufficient_titles.csv": "insufficient",
    }
)
_CATEGORY_FIELDS = frozenset(("招聘类别", "初级分类"))
_CONTAMINATION_FIELDS = frozenset(("recruitment_category", "initial_category"))
_CONTAMINATION_MATCH_TYPES = frozenset(("exact", "contains"))
_REQUIREMENT_PATTERN_TYPES = frozenset(
    ("salary_range", "experience_years", "education_requirement", "headcount", "age_range")
)
_OCCUPATION_MATCH_TYPES = frozenset(("exact", "suffix", "contains"))
_REVIEW_REASONS = frozenset(reason.value for reason in ReviewReason)
_PRIORITY = re.compile(r"[0-9]+\Z")
_SOURCE_QUALITY_CATEGORY_MODES = MappingProxyType(
    {
        "rail_air": frozenset(("literal_substring",)),
        "advertising_cue": frozenset(("literal_substring",)),
        "standalone_advertisement": frozenset(("segment_prefix", "segment_suffix")),
    }
)


@dataclass(frozen=True, slots=True)
class TextRule:
    rule_id: str
    pattern: str
    canonical_tag: str
    match_type: str
    priority: int
    action: str
    enabled: bool
    rationale: str
    source_filename: str
    source_row: int


RecruitmentRule = TextRule
TagRule = TextRule
ProtectedRule = TextRule


@dataclass(frozen=True, slots=True)
class NormalizationRule:
    rule_id: str
    pattern: str
    canonical_term: str
    match_type: str
    priority: int
    enabled: bool
    rationale: str
    source_filename: str
    source_row: int


@dataclass(frozen=True, slots=True)
class CategoryRule:
    rule_id: str
    field: str
    source_value: str
    clean_value: str
    category_type: CategoryType
    priority: int
    enabled: bool
    rationale: str
    source_filename: str
    source_row: int


@dataclass(frozen=True, slots=True)
class ReviewRule:
    rule_id: str
    title_pattern: str
    industry_values: tuple[str, ...]
    match_type: str
    review_reason: str
    enabled: bool
    rationale: str
    source_filename: str
    source_row: int

    @property
    def pattern(self) -> str:
        return self.title_pattern

    @property
    def priority(self) -> int:
        return 0


@dataclass(frozen=True, slots=True)
class SourceQualityRule:
    rule_id: str
    category: str
    term: str
    match_mode: str
    action: str
    enabled: bool
    rationale: str
    source_filename: str
    source_row: int


@dataclass(frozen=True, slots=True)
class RequirementRule:
    rule_id: str
    pattern_type: str
    literals: tuple[str, ...]
    units: tuple[str, ...]
    priority: int
    action: str
    enabled: bool
    rationale: str
    source_filename: str
    source_row: int


@dataclass(frozen=True, slots=True)
class OccupationMarkerRule:
    marker_id: str
    pattern: str
    match_type: str
    action: str
    enabled: bool
    rationale: str
    source_filename: str
    source_row: int


@dataclass(frozen=True, slots=True)
class MultiOccupationContextRule:
    rule_id: str
    source_prefix: str
    target_marker: str
    candidate_prefix: str
    enabled: bool
    rationale: str
    source_filename: str
    source_row: int


@dataclass(frozen=True, slots=True)
class ClassificationContaminationRule:
    rule_id: str
    field: str
    pattern: str
    match_type: str
    action: str
    enabled: bool
    rationale: str
    source_filename: str
    source_row: int


@dataclass(frozen=True, slots=True)
class RuleSet:
    version: str
    ruleset_hash: str
    recruitment: tuple[TextRule, ...]
    locations: tuple[TextRule, ...]
    employment: tuple[TextRule, ...]
    protected: tuple[TextRule, ...]
    normalization: tuple[NormalizationRule, ...]
    categories: tuple[CategoryRule, ...]
    review: tuple[ReviewRule, ...]
    source_quality: tuple[SourceQualityRule, ...]
    benefits: tuple[TextRule, ...]
    requirements: tuple[RequirementRule, ...]
    companies: tuple[TextRule, ...]
    job_codes: tuple[TextRule, ...]
    seniority: tuple[TextRule, ...]
    technical: tuple[TextRule, ...]
    location_protected: tuple[TextRule, ...]
    insufficient: tuple[TextRule, ...]
    occupation_markers: tuple[OccupationMarkerRule, ...]
    multi_occupation_context: tuple[MultiOccupationContextRule, ...]
    classification_contamination: tuple[ClassificationContaminationRule, ...]


def _error(filename: str, row: int | None, message: str) -> ValueError:
    location = filename if row is None else f"{filename}:{row}"
    return ValueError(f"{location}: {message}")


def _read_utf8_lf(path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise _error(path.name, None, "cannot be read") from error
    if data.startswith(b"\xef\xbb\xbf"):
        raise _error(path.name, None, "UTF-8 BOM is not allowed")
    if b"\r" in data:
        raise _error(path.name, None, "CR and CRLF line endings are not allowed")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _error(path.name, None, "must be valid UTF-8") from error
    return data


def _read_snapshot(rule_dir: Path) -> Mapping[str, bytes]:
    expected = frozenset(_SNAPSHOT_FILENAMES)
    try:
        found = frozenset(entry.name for entry in rule_dir.iterdir())
    except OSError as error:
        raise ValueError(f"{rule_dir}: rules directory cannot be read") from error
    if found != expected:
        raise ValueError(
            "rules directory: files must be exactly the version file and nineteen rule CSVs"
        )
    if any(not (rule_dir / name).is_file() for name in expected):
        raise ValueError("rules directory: every listed rule entry must be a file")
    return MappingProxyType({name: _read_utf8_lf(rule_dir / name) for name in _SNAPSHOT_FILENAMES})


def _load_versions(snapshot: Mapping[str, bytes]) -> str:
    filename = "rule_versions.json"
    raw = snapshot[filename]
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise _error(filename, None, "must be valid JSON") from error
    if not isinstance(value, dict) or set(value) != {"ruleset_version", "files"}:
        raise _error(filename, None, "must contain exactly ruleset_version and files")
    version = value["ruleset_version"]
    files = value["files"]
    if version != "v4":
        raise _error(filename, None, "ruleset_version must be v4")
    if not isinstance(files, list) or not all(isinstance(name, str) for name in files):
        raise _error(filename, None, "files must be a string array")
    if files != list(RULE_FILENAMES):
        raise _error(filename, None, "files must list each rule CSV once in canonical order")
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if raw != canonical.encode("utf-8"):
        raise _error(filename, None, "must use canonical JSON with one trailing LF")
    return version


def _read_csv(snapshot: Mapping[str, bytes], filename: str) -> tuple[dict[str, str], ...]:
    raw = snapshot[filename]
    raw_without_final_lf = raw[:-1] if raw.endswith(b"\n") else raw
    if any(line == b"" for line in raw_without_final_lf.split(b"\n")):
        raise _error(filename, None, "blank rows are not allowed")
    expected_header = list(RULE_FILE_HEADERS[filename])
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8")), strict=True)
        fieldnames = reader.fieldnames
    except csv.Error as error:
        raise _error(filename, 1, "malformed CSV") from error
    if fieldnames != expected_header:
        raise _error(filename, 1, "header must match the required columns and order")
    output: list[dict[str, str]] = []
    source_row = reader.line_num + 1
    previous_identifier: bytes | None = None
    try:
        for row in reader:
            if reader.line_num != source_row:
                raise _error(filename, source_row, "embedded line breaks are not allowed")
            if None in row or any(value is None for value in row.values()):
                raise _error(filename, source_row, "row must have exactly the required columns")
            values = {column: row[column] for column in expected_header}
            for column, value in values.items():
                if unicodedata.normalize("NFKC", value) != value:
                    raise _error(filename, source_row, f"{column} must be NFKC-stable")
                if value.strip() != value:
                    raise _error(filename, source_row, f"{column} must be trimmed")
            identifier = values[expected_header[0]].encode("utf-8")
            if previous_identifier is not None and identifier < previous_identifier:
                raise _error(filename, source_row, "rows must use canonical order by rule id")
            previous_identifier = identifier
            output.append(values)
            source_row = reader.line_num + 1
    except csv.Error as error:
        raise _error(filename, source_row, "malformed CSV") from error
    return tuple(output)


def _required(row: dict[str, str], column: str, filename: str, source_row: int) -> str:
    value = row[column]
    if not normalize_base(value):
        raise _error(filename, source_row, f"{column} must be nonblank")
    return value


def _parse_priority(row: dict[str, str], filename: str, source_row: int) -> int:
    priority = row["priority"]
    if not _PRIORITY.fullmatch(priority):
        raise _error(filename, source_row, "priority must be a nonnegative decimal integer")
    try:
        return int(priority)
    except ValueError as error:
        raise _error(
            filename, source_row, "priority must be a nonnegative decimal integer"
        ) from error


def _parse_enabled(row: dict[str, str], filename: str, source_row: int) -> bool:
    enabled = row["enabled"]
    if enabled not in {"true", "false"}:
        raise _error(filename, source_row, "enabled must be exactly true or false")
    return enabled == "true"


def _ensure_unique_identifier(
    identifiers: set[str], identifier: str, filename: str, source_row: int
) -> None:
    if identifier in identifiers:
        raise _error(filename, source_row, f"duplicate global rule or marker id {identifier!r}")
    identifiers.add(identifier)


def _parse_canonical_json_string_array(
    row: dict[str, str], column: str, filename: str, source_row: int
) -> tuple[str, ...]:
    raw = row[column]
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise _error(filename, source_row, f"{column} must be canonical JSON") from error
    if (
        not isinstance(value, list)
        or not all(isinstance(item, str) and normalize_base(item) for item in value)
        or len(value) != len(set(value))
        or value != sorted(value, key=lambda item: item.encode("utf-8"))
    ):
        raise _error(filename, source_row, f"{column} must be a sorted unique string array")
    canonical = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if raw != canonical:
        raise _error(filename, source_row, f"{column} must be canonical JSON")
    return tuple(value)


def _load_text_rules(
    snapshot: Mapping[str, bytes], filename: str, identifiers: set[str]
) -> tuple[TextRule, ...]:
    expected_action = _TEXT_RULE_ACTIONS[filename]
    rules: list[TextRule] = []
    for source_row, row in enumerate(_read_csv(snapshot, filename), start=2):
        rule_id = _required(row, "rule_id", filename, source_row)
        _ensure_unique_identifier(identifiers, rule_id, filename, source_row)
        match_type = row["match_type"]
        if match_type not in _TEXT_MATCH_TYPES:
            raise _error(filename, source_row, "match_type is not allowed for this rule file")
        if row["action"] != expected_action:
            raise _error(filename, source_row, "action is not allowed for this rule file")
        rules.append(
            TextRule(
                rule_id,
                _required(row, "pattern", filename, source_row),
                _required(row, "canonical_tag", filename, source_row),
                match_type,
                _parse_priority(row, filename, source_row),
                expected_action,
                _parse_enabled(row, filename, source_row),
                row["rationale"],
                filename,
                source_row,
            )
        )
    return tuple(rules)


def _load_normalization_rules(
    snapshot: Mapping[str, bytes], identifiers: set[str]
) -> tuple[NormalizationRule, ...]:
    filename = "normalization_terms.csv"
    rules: list[NormalizationRule] = []
    for source_row, row in enumerate(_read_csv(snapshot, filename), start=2):
        rule_id = _required(row, "rule_id", filename, source_row)
        _ensure_unique_identifier(identifiers, rule_id, filename, source_row)
        match_type = row["match_type"]
        if match_type not in _TEXT_MATCH_TYPES | {"latin_token"}:
            raise _error(filename, source_row, "match_type is not allowed for this rule file")
        pattern = _required(row, "pattern", filename, source_row)
        if match_type == "latin_token" and not is_latin_token_pattern(pattern):
            raise _error(
                filename, source_row, "latin_token pattern must use only ASCII token characters"
            )
        rules.append(
            NormalizationRule(
                rule_id,
                pattern,
                _required(row, "canonical_term", filename, source_row),
                match_type,
                _parse_priority(row, filename, source_row),
                _parse_enabled(row, filename, source_row),
                row["rationale"],
                filename,
                source_row,
            )
        )
    return tuple(rules)


def _load_category_rules(
    snapshot: Mapping[str, bytes], identifiers: set[str]
) -> tuple[CategoryRule, ...]:
    filename = "category_mappings.csv"
    rules: list[CategoryRule] = []
    category_keys: set[tuple[str, str]] = set()
    for source_row, row in enumerate(_read_csv(snapshot, filename), start=2):
        rule_id = _required(row, "rule_id", filename, source_row)
        if row["field"] not in _CATEGORY_FIELDS:
            raise _error(filename, source_row, "field must be 招聘类别 or 初级分类")
        try:
            category_type = CategoryType(row["category_type"])
        except ValueError as error:
            raise _error(
                filename, source_row, "category_type is not an existing CategoryType"
            ) from error
        if category_type is CategoryType.MISSING:
            if row["clean_value"]:
                raise _error(
                    filename, source_row, "clean_value must be empty for missing category_type"
                )
        else:
            _required(row, "source_value", filename, source_row)
            _required(row, "clean_value", filename, source_row)
        _ensure_unique_identifier(identifiers, rule_id, filename, source_row)
        enabled = _parse_enabled(row, filename, source_row)
        key = (normalize_base(row["field"]), normalize_base(row["source_value"]))
        if enabled and key in category_keys:
            raise _error(
                filename, source_row, "enabled category mapping key duplicates a normalized key"
            )
        if enabled:
            category_keys.add(key)
        rules.append(
            CategoryRule(
                rule_id,
                row["field"],
                row["source_value"],
                row["clean_value"],
                category_type,
                _parse_priority(row, filename, source_row),
                enabled,
                row["rationale"],
                filename,
                source_row,
            )
        )
    output = tuple(rules)
    compile_category_source_indexes(output)
    return output


def compile_category_source_indexes(
    rules: tuple[CategoryRule, ...],
) -> Mapping[str, Mapping[str, CategoryRule]]:
    """Validate category canonical values and build immutable exact-source indexes."""
    mutable_indexes: dict[str, dict[str, CategoryRule]] = {"招聘类别": {}, "初级分类": {}}
    for rule in rules:
        if not rule.enabled:
            continue
        if rule.field not in mutable_indexes:
            raise _error(
                rule.source_filename, rule.source_row, "field must be 招聘类别 or 初级分类"
            )
        source = normalize_base(rule.source_value)
        field_index = mutable_indexes[rule.field]
        if source in field_index:
            raise _error(
                rule.source_filename,
                rule.source_row,
                "enabled category mapping key duplicates a normalized key",
            )
        field_index[source] = rule
    for rule in rules:
        if not rule.enabled:
            continue
        clean = normalize_base(rule.clean_value)
        if not clean:
            continue
        self_rule = mutable_indexes[rule.field].get(clean)
        if (
            self_rule is None
            or normalize_base(self_rule.clean_value) != clean
            or self_rule.category_type is not rule.category_type
        ):
            raise _error(
                rule.source_filename,
                rule.source_row,
                "nonempty clean_value requires an enabled stable self-mapping",
            )
    return MappingProxyType(
        {field: MappingProxyType(field_index) for field, field_index in mutable_indexes.items()}
    )


def _load_review_rules(
    snapshot: Mapping[str, bytes], identifiers: set[str]
) -> tuple[ReviewRule, ...]:
    filename = "review_patterns.csv"
    rules: list[ReviewRule] = []
    for source_row, row in enumerate(_read_csv(snapshot, filename), start=2):
        rule_id = _required(row, "rule_id", filename, source_row)
        _ensure_unique_identifier(identifiers, rule_id, filename, source_row)
        if row["match_type"] not in _TEXT_MATCH_TYPES:
            raise _error(filename, source_row, "match_type is not allowed")
        if row["review_reason"] not in _REVIEW_REASONS:
            raise _error(filename, source_row, "review_reason is not allowed")
        industry_values = _parse_canonical_json_string_array(
            row, "industry_values", filename, source_row
        )
        is_industry_mismatch = row["review_reason"] == ReviewReason.TITLE_INDUSTRY_MISMATCH.value
        if is_industry_mismatch and not industry_values:
            raise _error(
                filename,
                source_row,
                "title_industry_mismatch requires nonempty industry_values",
            )
        if not is_industry_mismatch and industry_values:
            raise _error(
                filename,
                source_row,
                "industry_values are only allowed for title_industry_mismatch",
            )
        rules.append(
            ReviewRule(
                rule_id,
                _required(row, "title_pattern", filename, source_row),
                industry_values,
                row["match_type"],
                row["review_reason"],
                _parse_enabled(row, filename, source_row),
                row["rationale"],
                filename,
                source_row,
            )
        )
    return tuple(rules)


def _load_source_quality_rules(
    snapshot: Mapping[str, bytes], identifiers: set[str]
) -> tuple[SourceQualityRule, ...]:
    filename = "source_quality_terms.csv"
    rules: list[SourceQualityRule] = []
    semantic_keys: set[tuple[str, str, str]] = set()
    for source_row, row in enumerate(_read_csv(snapshot, filename), start=2):
        rule_id = _required(row, "rule_id", filename, source_row)
        _ensure_unique_identifier(identifiers, rule_id, filename, source_row)
        category = row["category"]
        match_mode = row["match_mode"]
        if category not in _SOURCE_QUALITY_CATEGORY_MODES:
            raise _error(filename, source_row, "category is not allowed")
        if match_mode not in _SOURCE_QUALITY_CATEGORY_MODES[category]:
            raise _error(filename, source_row, "match_mode is not allowed for category")
        if row["action"] != "flag_only":
            raise _error(filename, source_row, "action must be flag_only")
        term = _required(row, "term", filename, source_row)
        semantic_key = (category, term, match_mode)
        if semantic_key in semantic_keys:
            raise _error(filename, source_row, "duplicate source-quality semantic key")
        semantic_keys.add(semantic_key)
        rules.append(
            SourceQualityRule(
                rule_id,
                category,
                term,
                match_mode,
                "flag_only",
                _parse_enabled(row, filename, source_row),
                row["rationale"],
                filename,
                source_row,
            )
        )
    return tuple(rules)


def _load_requirement_rules(
    snapshot: Mapping[str, bytes], identifiers: set[str]
) -> tuple[RequirementRule, ...]:
    filename = "requirement_patterns.csv"
    rules: list[RequirementRule] = []
    for source_row, row in enumerate(_read_csv(snapshot, filename), start=2):
        rule_id = _required(row, "rule_id", filename, source_row)
        _ensure_unique_identifier(identifiers, rule_id, filename, source_row)
        if row["pattern_type"] not in _REQUIREMENT_PATTERN_TYPES:
            raise _error(filename, source_row, "pattern_type is not allowed")
        if row["action"] != "remove":
            raise _error(filename, source_row, "action must be remove")
        rules.append(
            RequirementRule(
                rule_id,
                row["pattern_type"],
                _parse_canonical_json_string_array(row, "literals", filename, source_row),
                _parse_canonical_json_string_array(row, "units", filename, source_row),
                _parse_priority(row, filename, source_row),
                "remove",
                _parse_enabled(row, filename, source_row),
                row["rationale"],
                filename,
                source_row,
            )
        )
    return tuple(rules)


def _load_occupation_marker_rules(
    snapshot: Mapping[str, bytes], identifiers: set[str]
) -> tuple[OccupationMarkerRule, ...]:
    filename = "occupation_markers.csv"
    rules: list[OccupationMarkerRule] = []
    for source_row, row in enumerate(_read_csv(snapshot, filename), start=2):
        marker_id = _required(row, "marker_id", filename, source_row)
        _ensure_unique_identifier(identifiers, marker_id, filename, source_row)
        if row["match_type"] not in _OCCUPATION_MATCH_TYPES:
            raise _error(filename, source_row, "match_type is not allowed")
        if row["action"] != "classify_only":
            raise _error(filename, source_row, "action must be classify_only")
        rules.append(
            OccupationMarkerRule(
                marker_id,
                _required(row, "pattern", filename, source_row),
                row["match_type"],
                "classify_only",
                _parse_enabled(row, filename, source_row),
                row["rationale"],
                filename,
                source_row,
            )
        )
    return tuple(rules)


def _load_multi_occupation_context_rules(
    snapshot: Mapping[str, bytes], identifiers: set[str]
) -> tuple[MultiOccupationContextRule, ...]:
    filename = "multi_occupation_context_rules.csv"
    rules: list[MultiOccupationContextRule] = []
    enabled_outputs: dict[tuple[str, str], str] = {}
    for source_row, row in enumerate(_read_csv(snapshot, filename), start=2):
        rule_id = _required(row, "rule_id", filename, source_row)
        _ensure_unique_identifier(identifiers, rule_id, filename, source_row)
        source_prefix = _required(row, "source_prefix", filename, source_row)
        target_marker = _required(row, "target_marker", filename, source_row)
        candidate_prefix = _required(row, "candidate_prefix", filename, source_row)
        enabled = _parse_enabled(row, filename, source_row)
        rationale = _required(row, "rationale", filename, source_row)
        key = (source_prefix, target_marker)
        previous_output = enabled_outputs.get(key)
        if enabled and previous_output is not None and previous_output != candidate_prefix:
            raise _error(
                filename,
                source_row,
                "enabled context rules map the same key to different candidate_prefix outputs",
            )
        if enabled:
            enabled_outputs[key] = candidate_prefix
        rules.append(
            MultiOccupationContextRule(
                rule_id,
                source_prefix,
                target_marker,
                candidate_prefix,
                enabled,
                rationale,
                filename,
                source_row,
            )
        )
    return tuple(rules)


def _load_contamination_rules(
    snapshot: Mapping[str, bytes], identifiers: set[str]
) -> tuple[ClassificationContaminationRule, ...]:
    filename = "classification_contamination_terms.csv"
    rules: list[ClassificationContaminationRule] = []
    for source_row, row in enumerate(_read_csv(snapshot, filename), start=2):
        rule_id = _required(row, "rule_id", filename, source_row)
        _ensure_unique_identifier(identifiers, rule_id, filename, source_row)
        if row["field"] not in _CONTAMINATION_FIELDS:
            raise _error(filename, source_row, "field is not allowed")
        if row["match_type"] not in _CONTAMINATION_MATCH_TYPES:
            raise _error(filename, source_row, "match_type is not allowed")
        if row["action"] != "flag_review":
            raise _error(filename, source_row, "action must be flag_review")
        rules.append(
            ClassificationContaminationRule(
                rule_id,
                row["field"],
                _required(row, "pattern", filename, source_row),
                row["match_type"],
                "flag_review",
                _parse_enabled(row, filename, source_row),
                row["rationale"],
                filename,
                source_row,
            )
        )
    return tuple(rules)


def load_rules(rule_dir: Path | str) -> RuleSet:
    """Validate the complete snapshot before publishing an immutable rule set."""
    snapshot = _read_snapshot(Path(rule_dir))
    version = _load_versions(snapshot)
    identifiers: set[str] = set()
    text_groups = {
        group: _load_text_rules(snapshot, filename, identifiers)
        for filename, group in _TEXT_RULE_GROUPS.items()
    }
    normalization = _load_normalization_rules(snapshot, identifiers)
    categories = _load_category_rules(snapshot, identifiers)
    review = _load_review_rules(snapshot, identifiers)
    source_quality = _load_source_quality_rules(snapshot, identifiers)
    requirements = _load_requirement_rules(snapshot, identifiers)
    occupation_markers = _load_occupation_marker_rules(snapshot, identifiers)
    multi_occupation_context = _load_multi_occupation_context_rules(snapshot, identifiers)
    classification_contamination = _load_contamination_rules(snapshot, identifiers)
    return RuleSet(
        version,
        _snapshot_hash(snapshot),
        text_groups["recruitment"],
        text_groups["locations"],
        text_groups["employment"],
        text_groups["protected"],
        normalization,
        categories,
        review,
        source_quality,
        text_groups["benefits"],
        requirements,
        text_groups["companies"],
        text_groups["job_codes"],
        text_groups["seniority"],
        text_groups["technical"],
        text_groups["location_protected"],
        text_groups["insufficient"],
        occupation_markers,
        multi_occupation_context,
        classification_contamination,
    )


def ruleset_hash(rule_dir: Path | str) -> str:
    """Return the byte-level SHA-256 identity of the complete versioned rule set."""
    return _snapshot_hash(_read_snapshot(Path(rule_dir)))


def _snapshot_hash(snapshot: Mapping[str, bytes]) -> str:
    """Return the byte-level SHA-256 identity of one immutable rule snapshot."""
    digest = hashlib.sha256()
    for filename in _SNAPSHOT_FILENAMES:
        payload = snapshot[filename]
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
    return digest.hexdigest()
