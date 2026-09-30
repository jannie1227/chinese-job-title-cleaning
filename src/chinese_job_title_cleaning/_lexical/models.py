"""Public data contracts for the job-title cleaning pipeline."""

from dataclasses import dataclass
from enum import StrEnum


INPUT_COLUMNS = ("record_id", "招聘岗位", "招聘类别", "初级分类", "上市公司行业")

CLEANED_RECORD_COLUMNS = (
    "record_id",
    "招聘岗位",
    "clean_title",
    "match_title_core",
    "招聘类别_raw",
    "招聘类别_clean",
    "招聘类别_type",
    "初级分类_raw",
    "初级分类_clean",
    "初级分类_type",
    "上市公司行业_raw",
    "上市公司行业_clean",
    "removed_terms",
    "location_tag",
    "company_tag",
    "seniority_tag",
    "employment_tag",
    "job_code_tag",
    "multi_occupation_flag",
    "information_sufficiency_flag",
    "source_quality_flag",
    "clean_actions",
    "clean_status",
    "review_reason",
    "cleaning_version",
    "ruleset_hash",
)

DICTIONARY_COLUMNS = (
    "match_item_id",
    "clean_title",
    "match_title_core",
    "招聘类别_clean",
    "初级分类_clean",
    "上市公司行业_clean",
    "freq",
)

BRIDGE_COLUMNS = ("record_id", "match_item_id")

MULTI_OCCUPATION_CANDIDATE_COLUMNS = (
    "record_id",
    "candidate_order",
    "candidate_title",
    "candidate_id",
)


class CleanStatus(StrEnum):
    UNCHANGED = "unchanged"
    CLEANED = "cleaned"
    REVIEW = "review"


class ReviewReason(StrEnum):
    UNSAFE_EMPTY_RESULT = "unsafe_empty_result"
    UNSAFE_LOCATION_REMOVAL = "unsafe_location_removal"
    PROTECTED_OVERLAP = "protected_overlap"
    MIXED_JOB_TITLE = "mixed_job_title"
    RULE_CONFLICT = "rule_conflict"
    MULTIPLE_OCCUPATIONS = "multiple_occupations"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    SUSPECTED_ADVERTISEMENT = "suspected_advertisement"
    TITLE_INDUSTRY_MISMATCH = "title_industry_mismatch"
    FEATURE_OVERLAP_CONFLICT = "feature_overlap_conflict"
    UNBALANCED_BRACKET = "unbalanced_bracket"
    UNKNOWN_HTML_ENTITY = "unknown_html_entity"
    UNKNOWN_SYMBOL = "unknown_symbol"
    CLASSIFICATION_CONTAMINATION = "classification_contamination"


class CleanAction(StrEnum):
    NORMALIZE_TITLE = "normalize_title"
    REMOVE_RECRUITMENT_PHRASE = "remove_recruitment_phrase"
    EXTRACT_LOCATION = "extract_location"
    REMOVE_LOCATION = "remove_location"
    EXTRACT_EMPLOYMENT = "extract_employment"
    REMOVE_EMPLOYMENT = "remove_employment"
    NORMALIZE_RECRUITMENT_CATEGORY = "normalize_recruitment_category"
    NORMALIZE_INITIAL_CATEGORY = "normalize_initial_category"
    NORMALIZE_INDUSTRY = "normalize_industry"
    DECODE_HTML_ENTITY = "decode_html_entity"
    CLEANUP_PUNCTUATION = "cleanup_punctuation"
    EXTRACT_COMPANY = "extract_company"
    EXTRACT_SENIORITY = "extract_seniority"
    EXTRACT_JOB_CODE = "extract_job_code"
    BUILD_MATCH_TITLE_CORE = "build_match_title_core"
    BUILD_CANDIDATE_CORE = "build_candidate_core"
    FLAG_MULTI_OCCUPATION = "flag_multi_occupation"
    FLAG_INSUFFICIENT_INFORMATION = "flag_insufficient_information"
    FLAG_SOURCE_QUALITY = "flag_source_quality"
    REMOVE_BRACKET_CONTENT = "remove_bracket_content"
    REMOVE_BENEFIT = "remove_benefit"
    REMOVE_REQUIREMENT = "remove_requirement"


class CategoryType(StrEnum):
    EMPLOYMENT_TYPE = "employment_type"
    JOB_FUNCTION = "job_function"
    PLATFORM_INDUSTRY = "platform_industry"
    MISSING = "missing"
    OTHER = "other"


class InformationSufficiency(StrEnum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"


class SourceQualityFlag(StrEnum):
    SUSPECTED_ADVERTISEMENT = "suspected_advertisement"
    TITLE_INDUSTRY_MISMATCH = "title_industry_mismatch"
    CLASSIFICATION_CONTAMINATION = "classification_contamination"


@dataclass(frozen=True, slots=True)
class RawRecord:
    """One source row using stable internal English attribute names."""

    record_id: str
    title: str
    recruitment_category: str
    initial_category: str
    industry: str


@dataclass(frozen=True, slots=True)
class CleanedRecord:
    """A cleaned row and its complete audit trail."""

    record_id: str
    title: str
    clean_title: str
    match_title_core: str
    recruitment_category_raw: str
    recruitment_category_clean: str
    recruitment_category_type: CategoryType
    initial_category_raw: str
    initial_category_clean: str
    initial_category_type: CategoryType
    industry_raw: str
    industry_clean: str
    removed_terms: tuple[str, ...]
    location_tag: tuple[str, ...]
    company_tag: tuple[str, ...]
    seniority_tag: tuple[str, ...]
    employment_tag: tuple[str, ...]
    job_code_tag: tuple[str, ...]
    multi_occupation_flag: bool
    information_sufficiency_flag: InformationSufficiency
    source_quality_flag: tuple[SourceQualityFlag, ...]
    clean_actions: tuple[CleanAction, ...]
    clean_status: CleanStatus
    review_reason: tuple[ReviewReason, ...]
    cleaning_version: str
    ruleset_hash: str
