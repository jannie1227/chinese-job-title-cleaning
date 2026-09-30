"""Complete general-worker benefit templates, without global word deletion.

Consumes the sealed v1.2.10 candidate. No record IDs, categories or industry
enter title parsing. Unknown tails, technical tasks and existing valid aliases
are unchanged. The synonym policy already exists in the cumulative standard.
"""
import json
import re
from functools import lru_cache
from . import revision_v1210 as previous

VERSION = 'routine_v1.6_standard_v1.2.11_dev'
PREFIX = re.compile(r'^(?:急聘|急招|招聘)?(普工(?:\s*/\s*操作工)?)')
SEPARATOR = re.compile(r'[\s,，、;；+\-—/]+')
WAGE = re.compile(r'(?:月入|底薪|月薪)\d+(?:\.\d+)?(?:[-~至]\d+(?:\.\d+)?)?[kK千万元]?|\d+(?:\.\d+)?(?:[kK千万元]|/天)')
BENEFITS = {
    '年底双薪','年终奖','厂区吃住','走结清','饭补','餐补','有餐补','有房补',
    '五险一金','五险','商业保险','意外险','补充医疗保险','企业年金',
    '小区宿舍','提供低价住宿','提供低价员工餐','包吃住','包三餐','包住','包吃',
    '加班费','全勤奖','高温补贴','夜班补助','工龄奖','法定节假日三薪','绩效奖金','日结',
}
BENEFIT = re.compile('|'.join(map(re.escape, sorted(BENEFITS, key=lambda x: (-len(x), x)))))
HOUSING = re.compile(r'(?:[一二三四五六七八九十单双1-9]人间|夫妻间|步行\d+(?:-\d+)?分钟(?:内)?)')
AMENITY = re.compile(r'WiFi|热水器|空调', re.I)
BRACKETS = {'(': ')', '[': ']', '【': '】'}


@lru_cache(maxsize=80000)
def parse(raw):
    raw = previous.base.norm(raw)
    m = PREFIX.match(raw)
    if not m:
        return None
    role = re.sub(r'\s+', '', m[1])
    rest = raw[m.end():]
    tokens = []; stack = []
    while rest:
        if rest[0] in BRACKETS:
            stack.append(BRACKETS[rest[0]]); rest = rest[1:]; continue
        if rest[0] in BRACKETS.values():
            if not stack or stack.pop() != rest[0]: return None
            rest = rest[1:]; continue
        hit = SEPARATOR.match(rest)
        if hit:
            rest = rest[hit.end():]; continue
        found = False
        for kind, pattern in [('benefit', BENEFIT), ('housing', HOUSING), ('wage', WAGE), ('amenity', AMENITY)]:
            hit = pattern.match(rest)
            if hit:
                tokens.append((kind, hit[0])); rest = rest[hit.end():]; found = True; break
        if found: continue
        if rest.startswith('男女') and any(v == '厂区吃住' for _, v in tokens):
            tokens.append(('recruitment_condition', '男女')); rest = rest[2:]; continue
        return None
    if stack or not tokens:
        return None
    amenities = {v.lower() for k, v in tokens if k == 'amenity'}
    # A lone product qualifier plus a salary is not sufficient benefit evidence.
    if amenities and not any(k in {'benefit', 'housing'} for k, _ in tokens) and len(amenities) < 2:
        return None
    return role, tuple(tokens)


def update(before):
    a = list(before); a[30] = VERSION
    if '普工' not in before[2]: return a, ()
    parsed = parse(before[2])
    if parsed is None: return a, ()
    role, tokens = parsed
    valid_cores = {'普工', '操作工'} if '/' in role else {'普工'}
    # Do not churn accepted synonyms or previously accepted conservative routes.
    if before[3] == role and before[4] in valid_cores and before[6] == '[]':
        return a, ()
    core = before[4] if before[4] in valid_cores else ('操作工' if '/' in role else '普工')
    a[3:7] = [role, core, 'SINGLE', '[]']
    events = ['T1211_COMPLETE_BENEFIT_TEMPLATE']
    if before[5:7] != a[5:7]: events.append('T1211_RESTORE_EXISTING_ALIAS_STRUCTURE')
    a[25:28] = previous.relation(a, before[25:28], True)
    # The shortened core must not hide an independently parsed identical alias
    # expression. All nonempty source leaves must agree; never select a handy
    # node from a mixed classification and never use industry as evidence.
    leaves = (*previous.semantic_base.leaves(tuple(a[9:15])), *previous.semantic_base.leaves(tuple(a[15:21])))
    if (role == '普工/操作工' and leaves and all(x == role for x in leaves)
            and not (a[14] or a[20]) and 'malformed' not in {a[11], a[17]}):
        a[25:28] = ['usable', 'auxiliary', '']
    if a[25:28] != before[25:28]: events.append('S1211_RECOMPUTE_AFTER_TITLE_CLEANUP')
    a[7] = 'COMPLETE_BENEFIT_TEMPLATE_V1211'
    a[8] = '|'.join(dict.fromkeys([x for x in before[8].split('|') if x] + events))
    return a, tuple(events)
