"""Depth-aware title repair over sealed v126; never uses review/record IDs.

Unknown nested occupational structures are retained but quarantined as UNSURE.
The candidate is not a semantic-quality certificate or a production export.
"""
import json
import re
from functools import lru_cache
from . import revision_v126 as previous

VERSION = 'routine_v1.6_standard_v1.2.7_dev'
base = previous.base
ENTITIES = {'蓝城中国', '金茂系'}
DEPARTMENT = re.compile(r'事业[一二三四五六七八九十百\d]+(?:部)?')
REGION_CODE = re.compile(r'[ -]+ZN(?:山东|中西南|浙沪|苏皖|常州)\d{1,3}$')
TRAVEL = re.compile(r'^出差(文员|配送员|司机|送货员|跟单员|仓管员)(.*)$')
MONEY = r'(?:\d+(?:\.\d+)?[wWkK万千]\d*|[一二两三四五六七八九十]+[万千][一二两三四五六七八九十]*)'
AD_NODES = {'大平台', '政策支持+市场良好', '热招', '外资500强', '全国有岗', '可年后到岗', '年后到岗', '无需', '单双轮休', '周六日', '坐班', '长白班', '无需经验'}
# Only co-occurring in an already recognized advertisement bracket. These are
# not free-standing global triggers (e.g. 专业培训 may itself be work content).
AD_COMPANIONS = {'机会多','精英共事','住宿','项目补贴','稳定','稳定发展','绩效奖','薪酬','有食堂','不卷假期长','导师带教','专业培训','可放宽学历'}
# Domains are not occupations. Exact constituent entries, not whole-title fixes.
TECH_QUALIFIERS = {
    'C','C++','Java','Python','Go','JS','Scala','Qt','UI','UX','Web测试',
    'Java开发','C开发','测试开发','自动化测试','功能测试','系统测试',
    '基带开发','电路设计','Camera','显示屏','应用开发','网络安全','大数据开发',
    '光机结构设计','镜头设计','全栈设计','解决方案','运营商能源',
    '数据建模','后端开发','SaaS','PaaS开发经验','系统','应急监测','主动运维','运维工具开发',
    '污水处理','设备调试','运营维护','采购管理','成本管理','财务管理','项目与计划管理',
    '电机结构设计','负责电机类产品机械结构设计','功能设计','车身电子功能开发',
    '运控系统开发','控制策略开发','底盘系统开发',
    '分子诊断原料','动物检测试剂','电力','金融','运营商',
    '环境','化工','市场营销','建筑减隔震','非销售','无销售','无销售性质','不带销售','不带外呼',
    '纯接听','无销售任务','文职','纯文职','审核后外呼确认',
    '不跑市场','不承担销售指标','非销售岗','销售内控','耗材','带人岗',
    '公众号','社群运营','B端','研发端','技术岗','外包岗','中级','应届','可小白',
    '兼职','短期用工','假期工','实习','应届生',
}
EXPLICIT_AMBIGUITY = re.compile(r'均有|均在|少量|兼(?!容|职)|一个偏向|普工|电工|钳工|架构师|讲师|研究员|测试经理|主任|班长|工段长')
ROLE_END = re.compile(r'(?:工程师|设计师|技术员|专员|经理|主管|总监|顾问|助理|文员|业务员|配送员|司机|送水员|客服|代表|销售|测试|开发|运营|招聘|会计|出纳|审计师|普工|主任师|主管师|班长|理货)$', re.I)
EMPLOYMENT_QUALIFIERS = {'兼职','短期用工','假期工','实习','应届生','可实习'}

def structure(text):
    """Balanced typed delimiters and top-level separators, not regex splitting."""
    opens = {'(': ')', '[': ']', '（': '）', '【': '】'}
    closes = set(opens.values())
    stack = []; separators = []; groups = []; start = None; valid = True
    for i, char in enumerate(text):
        if char in opens:
            if not stack: start = i
            stack.append(opens[char])
        elif char in closes:
            if not stack or stack[-1] != char:
                valid = False
            elif stack:
                stack.pop()
                if not stack: groups.append((start, i, text[start+1:i]))
        elif char in '/、,，' and not stack:
            separators.append(i)
    return not stack and valid, separators, groups

def broken_children(children):
    return any(not structure(x)[0] for x in children)

def outside(text):
    for start, end, _ in reversed(structure(text)[2]): text = text[:start]+text[end+1:]
    return text.strip()

def eligibility(a):
    t = a[3]; out = []
    if a[5] == 'C':
        ok, top, groups = structure(t)
        if broken_children(json.loads(a[6])) or (ok and not top and any(re.search(r'[/、,，]', x[2]) for x in groups)):
            out.append('NESTED_STRUCTURE')
        if re.fullmatch(r'.+项目经理/助理主任', t): out.append('SHARED_DOMAIN')
    if re.search(r'\((?:蓝城中国|金茂系|事业[一二三四五六七八九十百\d]+(?:部)?)\)', t): out.append('BOUNDED_ORGANIZATION')
    if REGION_CODE.search(t): out.append('BOUNDED_LOCATION_CODE')
    if TRAVEL.fullmatch(t): out.append('COMPLETE_TRAVEL_AD')
    if re.match(r'^甘宁青(?=学术|医药)',t):out.append('BOUNDED_LOCATION_CODE')
    if any('('+node in t for node in AD_NODES): out.append('BRACKET_AD')
    return out

def surface(s, raw):
    if not s: return s
    old = s
    def bracket(m):
        x = m[1]
        if x in ENTITIES or DEPARTMENT.fullmatch(x): return ''
        if x == '集团' and '集团急招' in raw:return ''
        # Preserve employment identity while removing the complete availability ad.
        if re.fullmatch(r'全国有岗\s+应届',x):return '(应届)'
        parts = re.split(r'[/、,，]', x)
        blocked = AD_NODES | AD_COMPANIONS if any(p.strip() in AD_NODES for p in parts) else AD_NODES
        kept = [p for p in parts if p.strip() not in blocked]
        if len(kept) != len(parts): return '('+'/'.join(kept)+')' if kept else ''
        return m[0]
    s = re.sub(r'\(([^()]*)\)', bracket, s)
    if raw.startswith('急聘'):s=re.sub(r'^急(?=普工$)','',s)
    if '邀您挑战高薪' in raw:s=re.sub(r'邀您挑战$','',s)
    s=re.sub(r'^招(?!聘)(?=.+(?:销售人员|工程师|专员)$)','',s)
    s = REGION_CODE.sub('', s)
    s = re.sub(r'^甘宁青(?=学术|医药)', '', s)
    m = TRAVEL.fullmatch(s)
    if m:
        role, tail = m.groups()
        salary = re.search(MONEY, raw) is not None
        known = tail == '' or tail == '可实习'
        known |= bool(re.fullmatch(MONEY+r'(?:长白|夫妻房)?', tail))
        known |= salary and tail in {'月','月常','吃住','2'}
        known |= tail in {'有','享'} and (tail+'五险') in raw
        known |= bool(re.fullmatch(MONEY+'交', tail)) and '交五险' in raw
        if known:
            s = role + ('(可实习)' if tail == '可实习' else '')
    return previous.tidy(s) if old != s else old

def qualifier_safe(text):
    if EXPLICIT_AMBIGUITY.search(text): return False
    tokens = re.split(r'[/、,，]', text)
    return bool(tokens) and all(re.sub(r'(?:专业|方向)$', '', t.strip()) in TECH_QUALIFIERS for t in tokens)

def outer_single(text):
    ok, top, groups = structure(text)
    if not ok or top or '兼' in outside(text): return False
    main = text
    for start, end, _ in reversed(groups): main = main[:start]+main[end+1:]
    return bool(ROLE_END.search(main.strip())) and all(qualifier_safe(x[2]) for x in groups)

def core(text):
    def bracket(m):
        parts=re.split(r'[/、,，]',m[1]);kept=[x for x in parts if x not in EMPLOYMENT_QUALIFIERS]
        return '('+'/'.join(kept)+')' if kept else ''
    return base.derive_core(re.sub(r'\(([^()]*)\)',bracket,text))

@lru_cache(maxsize=100000)
def title(raw, t, k, route, child_json):
    original = (t,k,route,child_json); raw = base.norm(raw)
    children = json.loads(child_json); events = []
    t, k = surface(t, raw), surface(k, raw)
    if (t,k) != original[:2]:
        events.append('T127_COMPLETE_BOUNDED_NOISE')
        children = [surface(x,raw) for x in children]
        if TRAVEL.fullmatch(original[0]) and re.fullmatch(r'(?:文员|配送员|司机|送货员|跟单员|仓管员)(?:\(可实习\))?',t):
            k = base.derive_core(t); route = 'SINGLE'; children = []
        if re.fullmatch(r'[\u4e00-\u9fff]{0,8}专场招聘会(?:\(年后到岗\))?',raw):
            t,k,route,children='专场招聘会','','X',[]
        if t in {'电子厂','电子厂寒假工'}:k,route,children='','UNSURE',[]
    if route == 'C':
        ok, top, groups = structure(t)
        # Existing complete nested job candidates are not erased by delimiter repair.
        complete = len(children)>=2 and all(structure(x)[0] and ROLE_END.search(outside(x)) for x in children)
        inner_only = ok and not top and any(re.search(r'[/、,，]',x[2]) for x in groups)
        if broken_children(children) or (inner_only and not complete):
            if outer_single(t):
                k, route, children = core(t), 'SINGLE', []
                events.append('T127_INNER_QUALIFIER_NOT_MULTI')
            else:
                # Do not invent a candidate from truncated fragments or mixed roles.
                k, route, children = '', 'UNSURE', []
                events.append('T127_MIXED_OR_BROKEN_STRUCTURE_HOLD')
        # Whole advertised wrapper containing explicit jobs; no category backfill.
        m = re.fullmatch(r'(?:500强|厂区|不出差\d+[+]?|速来电!)\((普工/技工|司机送货员/库管/装卸工/叉车工|销售经理/大客户代表)\)(?:当天办入职)?', t)
        if m:
            t, k, route, children = m[1], '', 'C', m[1].split('/')
            events.append('T127_AD_WRAPPER_EXPLICIT_JOBS')
    if route == 'C':
        m = re.fullmatch(r'(药代动力学|临床研究|药物分析)项目经理/助理主任', t)
        if m:
            children = [m[1]+'项目经理',m[1]+'助理主任']
            if children != json.loads(child_json): events.append('T127_SHARED_FUNCTIONAL_PREFIX')
    newjson = child_json if children == json.loads(child_json) else json.dumps(children,ensure_ascii=False)
    out = (t,k,route,newjson)
    return (out,tuple(dict.fromkeys(events))) if out != original else (original,())

def update(before):
    a=list(before); events=[]
    if eligibility(before):
        a[3:7], ev = title(before[2], *before[3:7]); events.extend(ev)
        if ev:
            a[25:28] = previous.relation(a,before[25:28],True,False)
            if a[25:28] != before[25:28]: events.append('S127_UPSTREAM_RELATION_RECOMPUTE')
            a[7]='DEPTH_AWARE_BOUNDED_RULES_V127'
            a[8]='|'.join(dict.fromkeys([x for x in before[8].split('|') if x]+events))
    a[30]=VERSION
    return a,tuple(dict.fromkeys(events))
