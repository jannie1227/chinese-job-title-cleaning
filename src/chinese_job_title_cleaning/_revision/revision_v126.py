"""Bounded, reusable v1.2.6 rules. No record identifiers or review lookups.

Sources are routed independently; titles only use the original title and
previous title fields. This is a development candidate, not quality approval.
"""
import json
import re
from functools import lru_cache
from . import revision_v12 as semantic

base = semantic.base
VERSION = 'routine_v1.6_standard_v1.2.6_dev'

# Typed entries have narrow positions/context; not a global brand eraser.
ENTITY_BRACKETS = {'安井美食', '芭薇化妆品', '华为安朴悦庭项目', '南大仙林'}
AD_BRACKETS = r'(?:全球(?:能源)?|世界)?(?:500|五百)强(?:项目)?|国有企业'
CODE_BRACKETS = r'others\d{3,8}|CLOU-RLZY\d{3,8}'
COMPLETE_AD = r'(?<![\w\u4e00-\u9fff])(?:提供车|系统派单)(?=$|[/ (),，])|(?:大小休|就业包分配|就近校区上班)(?=$|[/ (),，])'
ROLE_END = r'(?:专员|工程师|经理|主管|助理|总监|管理员|分析师|配送员|普工|业务|手工活|HRBP)$'
STAGE = r'实习生|应届生|储备干部|管培生'
ACTIVITIES = {'活动宣传', '配电柜报价', '养猪'}
BROAD_RELATION_HINTS = {'运营', '生产制造', '销售/客服/技术支持', '公务员/翻译'}
DISTINCT_PAIRS = {
    ('经理助理', '总值长'), ('星探', '主播经纪人'),
    ('活动主持', '活动督导'), ('普工', '质检'),
    ('质检', '设备工程师'), ('普工', '仓管'),
}
UNCERTAIN_PAIRS = {
    ('骑手', '配送员'), ('技术总监助理', 'CTO助理'),
    ('医药代表', '学术代表'), ('造价师', '预算师'),
}
SHARED_SOURCE = {
    '土木/土建/结构工程师': '土木工程师/土建工程师/结构工程师',
    '渠道/分销总监': '渠道总监/分销总监',
}
CONFLICT_PAIRS = (
    (r'(?:Java|C\+\+|Python|Golang|Go)?(?:软件|软件开发)工程师', r'仪器工程师'),
    (r'仿真工程师\((?:热学|力学)(?:/(?:热学|力学))?\)\s*电池研发', r'信息安全工程师'),
    (r'物流配送|配送员', r'海关事务管理|调度员'),
    (r'销售数据专员(?:\s*OTC)?', r'销售总监'),
    (r'生产运营副总经理', r'新闻副总编'),
)
CONSISTENT_PAIRS = (
    (r'普工', r'普工'),
    (r'Cocos(?:2d[- ]?x)?(?:开发)?工程师', r'软件工程师'),
    (r'渠道(?:营销)?总监', r'渠道总监|分销总监'),
    (r'(?:TD\s*)?高温工艺工程师\(炉管栅氧方向\)', r'半导体工艺工程师'),
    (r'涂装工艺开发岗(?:\(SE\))?', r'涂装工程师'),
)

def tidy(s):
    s = re.sub(r'\(\s*\)', '', s)
    s = re.sub(r'/{2,}', '/', s)
    return re.sub(r'\s+', ' ', s).strip(' /,，')

def surface(s, raw):
    """Apply only complete/noise-bounded phrases, retain unknown qualifiers."""
    if not s:
        return s
    original = s
    def bracket(m):
        x = m[1]
        if x in ENTITY_BRACKETS or re.fullmatch(AD_BRACKETS, x):
            return ''
        if re.fullmatch(CODE_BRACKETS, x, re.I):
            return ''
        if re.fullmatch(r'四季沐歌总部/(?:全球能源)?500强', x):
            return ''
        if x == '百度' and re.search(r'外派百度', raw):
            return ''
        if x == '三角' and '中山三角' in raw:
            return ''
        if re.fullmatch(r'非嘉兴岗位[,，]区域不限', x):
            return ''
        if x == '华舍员工公寓' and '华舍员工公寓事业部' in raw:
            return '(员工公寓)'
        if x == '成药营销中心':
            return '(成药营销)'
        # A repeated number is removed only if raw explicitly calls it a code.
        for code in re.findall(r'职位编号\s*[:：]\s*(\d+)', raw):
            if x.endswith(code) and re.fullmatch(r'[\u4e00-\u9fff]+', x[:-len(code)]):
                return '(' + x[:-len(code)] + ')'
        return m[0]
    s = re.sub(r'\(([^()]*)\)', bracket, s)
    s = re.sub(COMPLETE_AD, '', s)
    if '子女福利' in raw:
        s = re.sub(r'(?<= )子女(?= |$)', '', s)
    if re.search(r'^急{2,}', raw):
        s = re.sub(r'^急+(?=[\u4e00-\u9fff])', '', s)
    if re.search(r'\d+[千kK]到\d+[千kK]\+住', raw):
        s = re.sub(r'(?<=普工)到住$', '', s)
    if re.search(r'\d+[wW]\d+包(?:食宿|吃住)', raw):
        s = re.sub(r'\d+[wW]\d+$', '', s)
        s = re.sub(r'^出差(?=配送员)', '', s)
    if '手工活简单' in raw:
        s = re.sub(r'(?<=手工活)简单$', '', s)
    if '岗位多活轻松' in raw:
        s = re.sub(r'(?<=质检)活$', '', s)
    s = re.sub(r'(?<=[师员检])应聘$', '', s)
    s = re.sub(r'(?<=外贸业务)招聘$', '', s)
    # Only a delimited numbered department tail, after a complete role.
    m = re.fullmatch(r'(.+?)\s+\d+[\u4e00-\u9fff]{1,8}[一二三四五六七八九十\d]+部[一二三四五六七八九十\d]+课', s)
    if m and re.search(ROLE_END, m[1]):
        s = m[1]
    s = re.sub(r'^万科(?=物业)', '', s)
    if '驻小米' in raw:
        s = re.sub(r'驻小米(?=\(|$)', '', s)
    # Delimited county, not arbitrary substring geography deletion.
    s = re.sub(r'\s+滦县$', '', s)
    for term, target in [('ota', 'OTA'), ('mcu', 'MCU'), ('cocos', 'Cocos')]:
        end = r'(?![A-Za-z0-9])' if term != 'cocos' else r'(?=2[dD]|[^A-Za-z0-9]|$)'
        s = re.sub(r'(?<![A-Za-z])' + term + end, target, s, flags=re.I)
    # Formatting is a consequence of an actual targeted change, not a sweep
    # that pretends unresolved advertisement/parallel syntax is now repaired.
    return tidy(s) if s != original else original

@lru_cache(maxsize=100000)
def title(raw, t, k, route, child_json):
    original = (t, k, route, child_json)
    raw = base.norm(raw)
    oldt = t
    t, k = surface(t, raw), surface(k, raw)
    children = json.loads(child_json)
    events = []
    if t != oldt or k != original[1]:
        events.append('T126_BOUNDED_SURFACE')
        children = [surface(x, raw) for x in children]

    if re.fullmatch(r'(?:海外|国内|区域)(?:储备干部|管培生)', t):
        k, route, children = '', 'UNSURE', []
    if t and re.fullmatch(r'(?:\d{4})?届?校园招聘', raw):
        t, k, route, children = '校园招聘', '', 'X', []
    if re.fullmatch(r'(?:海外|国内)?信用卡中心', t):
        k, route, children = '', 'UNSURE', []
    if raw.startswith('非暑假工-电子厂轻松岗位') and t == '非暑假工':
        t, k, route, children = '电子厂(非暑假工)', '', 'UNSURE', []
    if re.fullmatch(r'家乡两地出差月\d+[wW]\d+', raw):
        t, k, route, children = '', '', 'X', []
    if re.fullmatch(STAGE, t):
        k, route, children = '', 'X', []
    m = re.fullmatch(r'(应届生|实习生)\s+方向[:：]?(.+)', t)
    if m and m[2] in ACTIVITIES:
        t, k, route, children = m[2] + m[1], m[2], 'UNSURE', []
    m = re.fullmatch(r'(活动宣传|配电柜报价|养猪)(?:达人)?(' + STAGE + r')', t)
    if m:
        t, k, route, children = m[1] + m[2], m[1], 'UNSURE', []
    # Bilingual equivalents are a typed translation, not arbitrary suffix loss.
    m = re.fullmatch(r'(高级)?产品工程师\(?Senior Product Engineer\)?', t, re.I)
    if m:
        t, k = (m[1] or '') + '产品工程师(Senior Product Engineer)', '产品工程师'
    if re.search(r'Linux/WindowsC\+$', raw) and t.endswith('Linux/WindowsC)'):
        t = t[:-1] + '+)'
        if k.endswith('Linux/WindowsC)'):
            k = k[:-1] + '+)'

    # Fully bounded recruitment wrapper; never infer role from employer.
    m = re.fullmatch(r'[^,，/]{2,20}新开部门订单增多[,，]招聘(普工)[,，](仓管)[,，]长白班', raw)
    if m:
        t, k, route, children = '/'.join(m.groups()), '', 'C', list(m.groups())
    main = re.sub(r'\([^()]*\)$', '', t)
    pair = tuple(main.split('/'))
    if pair in DISTINCT_PAIRS:
        k, route, children = '', 'C', list(pair)
    elif pair in UNCERTAIN_PAIRS:
        k, route, children = '', 'UNSURE', []
    if re.fullmatch(r'(?:C\+\+|Java|Python)(?:[、/](?:C\+\+|Java|Python))+/软件开发/测试', t):
        k, route, children = '', 'UNSURE', []
    if re.fullmatch(r'.*店长项目主管/经理', t):
        raw_main = raw.split('(')[0]
        if raw_main == t.replace('/', ''):
            t = raw_main
        k, route, children = '', 'UNSURE', []
    if route == 'C':
        m = re.fullmatch(r'(京东|天猫|淘宝)店长/运营', t)
        if m:
            children = [m[1] + '店长', m[1] + '运营']
        m = re.fullmatch(r'(.+研究院|研究院)院长/副院长', t)
        if m:
            children = [m[1] + '院长', m[1] + '副院长']
    # Restore generic management scope only when the entire raw sequence parses.
    management = re.sub(r'\(大唐财富\)$', '', raw)
    token = r'(?:分公司|业务部|城市|营业部)(?:总经理|经理)'
    if re.fullmatch(r'(?:' + token + r'){2,5}', management):
        children = re.findall(token, management)
        t, k, route = '/'.join(children), '', 'C'
    if (k, route) != original[1:3] and t == oldt:
        events.append('T126_CORE_OR_STRUCTURE')
    elif (t, k, route) != original[:3] and 'T126_BOUNDED_SURFACE' not in events:
        events.append('T126_RAW_STAGE_OR_STRUCTURE')
    out_json = child_json if children == json.loads(child_json) else json.dumps(children, ensure_ascii=False)
    if out_json != child_json:
        events.append('T126_PARALLEL_CANDIDATES')
    out = (t, k, route, out_json)
    return (out, tuple(dict.fromkeys(events))) if out != original else (original, ())

@lru_cache(maxsize=10000)
def source(values):
    raw, clean, route, occ, industry, unparsed = values
    s = base.norm(raw).replace('_', '/')
    channel = ''
    if s in SHARED_SOURCE:
        route, occ, industry, unparsed = 'occupation_taxonomy', SHARED_SOURCE[s], '', ''
    elif re.fullmatch(r'(?:\d{4}届)?校园招聘\(制造类\)', s):
        route, occ, industry, unparsed, channel = 'mixed', '', '制造', '', '校园招聘'
    return (raw, clean, route, occ, industry, unparsed), channel

def leaves(values):
    raw = base.norm(values[0]).replace('_', '/')
    if raw in SHARED_SOURCE:
        return tuple(SHARED_SOURCE[raw].split('/'))
    return base.concrete_leaves(values[0], values[3])

def relation(a, old, changed, source_changed):
    if a[11] == 'malformed' or a[17] == 'malformed':
        return old
    if not a[23]:
        safe = {'employment_type', 'recruitment_channel', 'source_industry', 'mixed', 'missing', 'unspecified'}
        if a[11] in safe and a[17] in safe and not (a[14] or a[20]):
            substantive_emp = set(a[21].split('/')) & {'全职', '兼职', '临时', '实习'}
            if (source_changed or old[0] == 'unspecified') and (substantive_emp or a[22] or a[24]):
                return ['usable', 'none', '']
        return old
    if not a[4] or a[5] in {'C', 'X'}:
        return ['weak', 'candidate_expansion_only', 'TITLE_NOT_READY'] if changed else old
    ls = tuple(x for x in (*leaves(tuple(a[9:15])), *leaves(tuple(a[15:21]))) if x not in base.BROAD_PARENTS)
    # All independently extracted leaves must be accounted for. A broad or
    # unrelated extra node blocks promotion; never choose only a matching leaf.
    for title_pattern, hint_pattern in CONSISTENT_PAIRS:
        if ls and re.fullmatch(title_pattern, a[4], re.I) and all(re.fullmatch(hint_pattern, x, re.I) for x in ls):
            return ['usable', 'auxiliary', '']
    for title_pattern, hint_pattern in CONFLICT_PAIRS:
        if ls and re.fullmatch(title_pattern, a[4], re.I) and all(re.fullmatch(hint_pattern, x, re.I) for x in ls):
            return ['conflict', 'disabled', 'OCCUPATION_CONFLICT']
    result, _ = semantic.relation(a[4], a[5], tuple(a[9:15]), tuple(a[15:21]), a[23], a[24], a[21], a[22], tuple(old), changed)
    result = list(result)
    if changed and old[2] == 'TITLE_NOT_READY' and result[0] == 'weak':
        broad = a[23] in BROAD_RELATION_HINTS
        result = ['weak', 'candidate_expansion_only', ('BROAD_CATEGORY|' if broad else '') + 'OCCUPATION_RELATION_UNCERTAIN']
    # Repaired shared occupation suffixes are concrete roles, not the former
    # isolated broad fragment. Do not infer breadth from a slash in a domain
    # qualifier such as 场长(农/林/牧/渔).
    occ_sources = [v for v in (tuple(a[9:15]), tuple(a[15:21])) if v[3]]
    if source_changed and occ_sources and all(base.norm(v[0]).replace('_', '/') in SHARED_SOURCE for v in occ_sources) and result[0] == 'weak':
        result[2] = '|'.join(x for x in result[2].split('|') if x != 'BROAD_CATEGORY')
    return result

def probe(a):
    """Eligibility pools include unchanged examples, not just actual diffs."""
    out = []
    if re.search(r'[()（）/]|储备|实习|应届|校园|急|大小休|招聘|驻|万科|[A-Za-z]', a[2]):
        out.append('TITLE_ELIGIBLE')
    if re.search(r'工程师|总监|校园招聘', a[9] + '/' + a[15]):
        out.append('SOURCE_ELIGIBLE')
    if a[23] or (a[21] and not a[23]):
        out.append('RELATION_ELIGIBLE')
    return out

def update(before):
    a = list(before)
    a[3:7], ev = title(before[2], *before[3:7])
    events = list(ev)
    source_changed = False
    for i in (9, 15):
        val, channel = source(tuple(before[i:i+6]))
        a[i:i+6] = val
        if list(val) != before[i:i+6]:
            source_changed = True
            events.append('C126_INDEPENDENT_SOURCE')
        if channel:
            a[22] = base.join_values((a[22], channel))
    if source_changed:
        a[23] = base.join_values((a[12], a[18]))
        a[24] = base.join_values((a[13], a[19]))
    a[25:28] = relation(a, before[25:28], bool(ev) or source_changed, source_changed)
    if a[25:28] != before[25:28]:
        events.append('S126_RELATION_RECOMPUTE')
    if ev:
        a[7] = 'BOUNDED_COMMON_RULES_V126'
    if events:
        a[8] = '|'.join(dict.fromkeys([x for x in before[8].split('|') if x] + events))
    a[30] = VERSION
    return a, tuple(dict.fromkeys(events))
