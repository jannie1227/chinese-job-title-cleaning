"""Pure normalization for job-matching category and industry metadata."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from chinese_job_title_cleaning._lexical.models import (
    CategoryType,
    CleanAction,
    ReviewReason,
    SourceQualityFlag,
)
from chinese_job_title_cleaning._lexical.normalize import normalize_base
from chinese_job_title_cleaning._lexical.rules import (
    CategoryRule,
    ClassificationContaminationRule,
    RuleSet,
    compile_category_source_indexes,
)
from chinese_job_title_cleaning._lexical.title_structure import normalize_entities


_CATEGORY_ACTIONS = {
    "招聘类别": CleanAction.NORMALIZE_RECRUITMENT_CATEGORY,
    "初级分类": CleanAction.NORMALIZE_INITIAL_CATEGORY,
}
_FIELD_ACTIONS = {
    **_CATEGORY_ACTIONS,
    "上市公司行业": CleanAction.NORMALIZE_INDUSTRY,
}
_CONTAMINATION_FIELDS = {
    "招聘类别": "recruitment_category",
    "初级分类": "initial_category",
}
_PLACEHOLDERS = frozenset(("不限", "无", "未知", "n/a", "na", "null", "-"))
_CONTAMINATION_CHARACTERS = frozenset("?<>_")
CategoryNormalization = tuple[str, str, CategoryType, CleanAction | None]
IndustryNormalization = tuple[str, str, CleanAction | None]


@dataclass(frozen=True, slots=True)
class MetadataResult:
    """One independently normalized metadata field and its audit signals."""

    raw: str
    clean: str
    type: CategoryType | None
    action: CleanAction | None
    source_quality_flags: tuple[SourceQualityFlag, ...]
    review_reasons: tuple[ReviewReason, ...]


@dataclass(frozen=True, slots=True)
class MetadataNormalizer:
    """Reusable immutable indexes compiled before streaming any records."""

    recruitment_category_index: Mapping[str, CategoryRule]
    initial_category_index: Mapping[str, CategoryRule]
    classification_contamination_rules: tuple[ClassificationContaminationRule, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "recruitment_category_index",
            MappingProxyType(dict(self.recruitment_category_index)),
        )
        object.__setattr__(
            self,
            "initial_category_index",
            MappingProxyType(dict(self.initial_category_index)),
        )
        object.__setattr__(
            self,
            "classification_contamination_rules",
            tuple(self.classification_contamination_rules),
        )


def compile_metadata_normalizer(rule_set: RuleSet) -> MetadataNormalizer:
    """Validate and compile category rules once, before record processing."""
    indexes = compile_category_source_indexes(rule_set.categories)
    return MetadataNormalizer(
        recruitment_category_index=indexes["招聘类别"],
        initial_category_index=indexes["初级分类"],
        classification_contamination_rules=rule_set.classification_contamination,
    )


def normalize_metadata(raw: str, field: str, normalizer: MetadataNormalizer) -> MetadataResult:
    """Normalize one metadata field without title rules or cross-field inference."""
    try:
        action_type = _FIELD_ACTIONS[field]
    except KeyError as error:
        raise ValueError("field must be 招聘类别, 初级分类, or 上市公司行业") from error

    structure = normalize_entities(raw)
    clean = structure.text
    category_type: CategoryType | None = None
    if _is_placeholder(clean):
        clean = ""

    if field in _CATEGORY_ACTIONS:
        source_rules = (
            normalizer.recruitment_category_index
            if field == "招聘类别"
            else normalizer.initial_category_index
        )
        if not clean:
            category_type = CategoryType.MISSING
        else:
            rule = source_rules.get(clean)
            if rule is None:
                category_type = CategoryType.OTHER
            else:
                clean = normalize_base(rule.clean_value)
                category_type = rule.category_type

    contaminated = field in _CONTAMINATION_FIELDS and _is_contaminated(
        clean,
        _CONTAMINATION_FIELDS[field],
        normalizer.classification_contamination_rules,
    )
    flags = (SourceQualityFlag.CLASSIFICATION_CONTAMINATION,) if contaminated else ()
    reason_set = set(structure.review_reasons)
    if contaminated:
        reason_set.add(ReviewReason.CLASSIFICATION_CONTAMINATION)
    reasons = tuple(reason for reason in ReviewReason if reason in reason_set)
    return MetadataResult(
        raw,
        clean,
        category_type,
        action_type if raw != clean else None,
        flags,
        reasons,
    )


def normalize_category(
    raw: str, field: str, normalizer: MetadataNormalizer
) -> CategoryNormalization:
    """Normalize one approved category field without cross-field inference.

    The first tuple item is always the unmodified source value. This compatibility
    API exposes the category subset of :func:`normalize_metadata`.
    """
    if field not in _CATEGORY_ACTIONS:
        raise ValueError("field must be 招聘类别 or 初级分类")
    result = normalize_metadata(raw, field, normalizer)
    assert result.type is not None
    return result.raw, result.clean, result.type, result.action


def normalize_industry(
    raw: str, normalizer: MetadataNormalizer | None = None
) -> IndustryNormalization:
    """Apply format-only normalization to industry, preserving its source value."""
    if normalizer is None:
        clean = normalize_entities(raw).text
        if _is_placeholder(clean):
            clean = ""
        action = CleanAction.NORMALIZE_INDUSTRY if raw != clean else None
        return raw, clean, action
    result = normalize_metadata(raw, "上市公司行业", normalizer)
    return result.raw, result.clean, result.action


def _is_placeholder(value: str) -> bool:
    return value.lower() in _PLACEHOLDERS


def _is_contaminated(
    value: str,
    field: str,
    rules: tuple[ClassificationContaminationRule, ...],
) -> bool:
    if any(character in value for character in _CONTAMINATION_CHARACTERS):
        return True
    return any(
        rule.enabled
        and rule.field == field
        and (
            (rule.match_type == "exact" and value == rule.pattern)
            or (rule.match_type == "contains" and rule.pattern in value)
        )
        for rule in rules
    )
