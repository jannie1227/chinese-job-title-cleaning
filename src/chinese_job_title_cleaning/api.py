"""两个明确分开的接口：通用词法清洗，以及研究 v1.2.12 末轮修订。

通用接口只需要调用者自己的字符串，采用已有公开词法核心 0.4.0 / v4
词典。它不使用私有原文定案，也不声称重建研究终版或完成职业赋码。
"""
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

from ._lexical.classify_metadata import compile_metadata_normalizer, normalize_metadata
from ._lexical.rules import load_rules
from ._lexical.title_cleaner import clean_title as lexical_clean_title
from ._frozen_revision import HEADERS, routing
from ._revision import revision_v1212


def _string(value, field):
    if not isinstance(value, str):
        raise TypeError(field + ' must be a string; convert missing values explicitly.')
    return value


class TitleCleaner:
    """重复使用同一公开词典处理职位与四字段；初始化不联网、不读取数据。

    ``rules_dir`` 可指向调用者自己的同结构规则目录；默认规则随 wheel
    安装，离开项目工作目录也可以调用。原字符串始终放在 *_raw 字段中。
    """
    def __init__(self, rules_dir=None):
        self.rules = load_rules(Path(rules_dir) if rules_dir else Path(__file__).parent / 'data_rules')
        self.metadata = compile_metadata_normalizer(self.rules)

    def clean_title(self, title: str) -> str:
        """返回去除明确词法噪声后的标题；空输入返回空字符串。"""
        return self.clean_record(title)['clean_title']

    def clean_record(self, title: str, *, record_id='', recruitment_category='', initial_category='', industry='') -> dict:
        """返回 JSON 可序列化字典：原值、清洗值、类型、操作、复核原因。

        分类字段分别标准化，不根据标题或行业猜填缺失分类。行业仅做
        格式处理。此方法不推断 SOC、不删除记录、不生成职业就绪结论。
        """
        for field, value in [('title',title),('record_id',record_id),('recruitment_category',recruitment_category),('initial_category',initial_category),('industry',industry)]:
            _string(value, field)
        if title.strip():
            cleaned = lexical_clean_title(title, self.rules)
            value = cleaned.clean_title
            removed = list(cleaned.removed_terms)
            locations = list(cleaned.location_tag)
            employment = list(cleaned.employment_tag)
            actions = [x.value for x in cleaned.clean_actions]
            reasons = [x.value for x in cleaned.review_reason]
            status = cleaned.clean_status.value
        else:
            value, removed, locations, employment, actions, reasons, status = '', [], [], [], [], ['empty_title'], 'review'
        result = {'record_id':record_id,'title_raw':title,'clean_title':value,'removed_terms':removed,'location_tag':locations,'employment_tag':employment}
        for name, raw, field in [('recruitment_category',recruitment_category,'招聘类别'),('initial_category',initial_category,'初级分类'),('industry',industry,'上市公司行业')]:
            normalized = normalize_metadata(raw, field, self.metadata)
            result[name + '_raw'] = raw
            result[name + '_clean'] = normalized.clean
            if name != 'industry':
                result[name + '_type'] = normalized.type.value
            if normalized.action:
                actions.append(normalized.action.value)
            reasons.extend(x.value for x in normalized.review_reasons)
        reasons = list(dict.fromkeys(reasons))
        if reasons:
            status = 'review'
        elif actions:
            status = 'cleaned'
        result.update(clean_actions=list(dict.fromkeys(actions)),clean_status=status,review_reason=reasons,rule_scope='public_lexical_v4',ruleset_hash=self.rules.ruleset_hash)
        return result

    def iter_clean_records(self, records: Iterable[Mapping]) -> Iterable[dict]:
        """逐条输出，不按相同标题合并；未提供 ID 时按输入顺序生成 ID。"""
        seen = set()
        for number, row in enumerate(records, 1):
            if not isinstance(row, Mapping) or 'title' not in row:
                raise ValueError('Each record must be a mapping with a title field.')
            record_id = row.get('record_id', f'PUBLIC_{number:010d}')
            _string(record_id, 'record_id')
            if not record_id or record_id in seen:
                raise ValueError('record_id must be nonempty and unique.')
            seen.add(record_id)
            yield self.clean_record(row['title'],record_id=record_id,recruitment_category=row.get('recruitment_category',''),initial_category=row.get('initial_category',''),industry=row.get('industry',''))

    def clean_records(self, records: Iterable[Mapping]) -> list[dict]:
        """小批量便利接口；大文件使用 iter_clean_records 或命令行入口。"""
        return list(self.iter_clean_records(records))


@lru_cache(maxsize=1)
def _default():
    return TitleCleaner()


def clean_title(title: str) -> str:
    """用随包规则清洗一个普通职位字符串。"""
    return _default().clean_title(title)


def clean_record(title: str, **metadata) -> dict:
    """用随包规则清洗一个普通职位和可选分类字段。"""
    return _default().clean_record(title, **metadata)


def clean_records(records: Iterable[Mapping]) -> list[dict]:
    """批量清洗普通记录；保留每条输入和重复标题。"""
    return _default().clean_records(records)


def revise_record(record: Mapping, *, pending=False) -> dict:
    """研究接口：输入必须包含 v1.2.11 的 31 个封存字段。

    与通用 clean_record 分开，避免把早期词法清洗冒称为终版复现。
    ``pending`` 由持有私有未决组合规则的调用者提供；不从标题猜测。
    """
    if not isinstance(record, Mapping) or any(name not in record for name in HEADERS):
        raise ValueError('Research revision requires all 31 v1.2.11 fields.')
    before = [_string(record[name], name) for name in HEADERS]
    after, events = revision_v1212.update(before)
    flag = 'AI_KNOWN_UNRESOLVED' if pending else ''
    result = dict(zip(HEADERS, after))
    result.update(zip(['soc_input_route','occupation_hint_auxiliary','occupation_hint_candidates_only','known_pending_issue'],routing(after, flag)))
    result['revision_events'] = list(events)
    return result
