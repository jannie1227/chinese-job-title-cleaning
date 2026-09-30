"""Source-grounded closeout of established v129 issues, never keyed by record ID.

This layer consumes a sealed v129 result.  It does not rerun or mutate the
historical pipeline.  Title parsing cannot inspect classifications or industry.
Populated UNSURE cores are not globally upgraded.  Unknown structures survive.
"""
import json
import re
from functools import lru_cache
from . import revision_v129 as old
from . import revision_v126 as semantic_base

VERSION = 'routine_v1.6_standard_v1.2.10_dev'
base = old.base
FIELDS = tuple(range(3, 7)) + tuple(range(25, 28))
ROLE_END = re.compile(r'(?:工程师|设计师|经理|主管|总监|专员|顾问|技师|技术员|操作工|维修工|焊工|服务员|管理员|客服管家|实习生|稽核岗)$')
BRACKET_EMPLOYERS = {'凹凸租车', '海创科技中心', '德信房产', '赴麦子金服'}
WORK_PLACES = {'五洲城', '工作地阳江'}
BRACKET_AD = re.compile(r'(?:可接受出差|近地铁|高收入|双休|项目稳定|港企不加班|不加班)(?:[+ /、](?:可接受出差|近地铁|高收入|双休|项目稳定|港企不加班|不加班))*')
ACTIVITIES = {'法医鉴定', '证券事务', '文本标注', '数控车铣技术', '实施'}
TRIGGER = re.compile(r'华勤|暑假工/学习工|不要求有证件|上班|BG|凯里亚德|前海|凹凸租车|CoCo|营销委|乘风工作室|五矿绿城|大唐财富|可接受出差|技术研究院|。|贵阳院|细胞治疗|优秀员工奖|十强|Assembly|医药开票|研发[一二三四五六七八九十\d]+部|可培养|大团队|海拉车灯|营销类|海创科技|五洲城|科达机电|核心团队|可学习|运作部|scrum|大朗|房产精英|ZF电子厂|泰山7号|pcr|链家同业|夫妻房|退休返聘|对日|项目稳定|项目成本|代建板块|急聘|集团财务|实习生|储备干部|储备经理人|数控车铣|婚恋|基金大客户部|特变电工|麦子金服|业务序列岗|不开车|稽核岗\d')


def tidy(s):
    return re.sub(r'\s+', ' ', re.sub(r'\(\s*\)', '', s)).strip(' /、,，-—')


def stages_only(raw):
    """Exhaustive known employer/benefit template; return actual stage captures.

    None means not parsed.  Empty string means fully parsed, no occupation and
    no stage.  Optional groups are NEVER replaced with a constant pair of jobs.
    """
    if not raw.startswith('华勤'):
        return None
    rest = raw[2:]
    token = re.compile(r'直招|暑假工|学习工|正式工|长期工|坐班|长白班|工作轻松|不穿无尘服|包吃住|工资高|美女多|\d+(?:\.\d+)?/天|[/、,，\s]+')
    stages = []
    while rest:
        m = token.match(rest)
        if not m:
            return None
        if m[0] in {'暑假工', '学习工', '正式工', '长期工'}:
            stages.append(m[0])
        rest = rest[m.end():]
    return '/'.join(dict.fromkeys(stages))


def pure_ad(raw):
    patterns = (
        r'L?海拉车灯全市班车五险一(?:金)?',
        r'ZF电子厂\s*(?:包吃住)?年底结清',
        r'白班\d+(?:\.\d+)?[千万元]起包吃住有夫妻房',
        r'欢迎链家同业人员加入底薪\d+(?:-\d+)?加提成',
    )
    return any(re.fullmatch(p, raw, re.I) for p in patterns)


def surface(s, raw):
    if not s:
        return s
    start = s
    # All removals have a complete phrase or an independently typed boundary.
    s = re.sub(r'不要求有证件$', '', s)
    if re.search(r'上班轻松\d+(?:\.\d+)?/小时', raw):
        s = re.sub(r'(?<=工)上班$', '', s)
    s = re.sub(r'(?<=[工员师])。+$', '', s)
    s = re.sub(r'^可培养[—\-\s]+', '', s)
    s = re.sub(r'\s*优秀员工奖$', '', s)
    s = re.sub(r'(?<=维修工)可学习$', '', s)
    s = re.sub(r'(?<=[师员工)])\s*(?:营销委|研发[一二三四五六七八九十\d]+部|技术研究院)$', '', s)
    s = re.sub(r'(?<=岗)\s+营销类$', '', s)
    if re.search(r'[-—]乘风工作室', raw):
        s = re.sub(r'\s*乘风工作室$', '', s)
    if raw.startswith('凯里亚德酒店'):
        s = re.sub(r'^(?:凯里)?亚德(?=酒店)', '', s)
    if raw.startswith('五矿绿城御园'):
        s = re.sub(r'^五矿绿城御园(?=销售代表)', '', s)
    if raw.startswith('贵阳院招聘'):
        s = re.sub(r'^(?:贵阳)?院招聘(?=服务员)', '', s)
    if raw.startswith('CoCo茶'):
        s = re.sub(r'^CoCo(?=茶)', '', s)
    if re.search(r'[-—]大唐财富', raw):
        s = re.sub(r'\s*大唐财富$', '', s)
    if re.match(r'^大朗[-—]', raw):
        s = re.sub(r'^大朗\s*(?=电工)', '', s)
    if '泰山7号' in raw:
        s = re.sub(r'^7号(?=客服管家)', '', s)
    if raw.startswith('外运物流') and '运作部' in raw:
        s = re.sub(r'^运作(?=仓库管理员)', '', s)
    if raw.startswith('急聘'):
        s = re.sub(r'^急(?=普工|操作工)', '', s)
    s = re.sub(r'^聘(?=储备经理人$)', '', s)
    s = re.sub(r'(?<=实习生)\s*(?:\d{2,4}届)?优秀[\u4e00-\u9fff]{0,8}(?:硕士|本科|博士|专科)可投递[!！]*$', '', s)
    # Three-digit and longer suffix codes, only after specified role endings.
    m = re.fullmatch(r'(.*(?:稽核岗|实习生))(\d{3,6})', s)
    if m and m[0] in raw:
        s = m[1]
    s = re.sub(r'^pcr(?=技术员$)', 'PCR', s, flags=re.I)
    s = re.sub(r'^scrum\s+master$', 'Scrum Master', s, flags=re.I)
    # Business-group labels retain their actual business domain.
    s = re.sub(r'\s+教育BG$', '(教育)', s)
    if '前海超高层项目' in raw:
        s = s.replace('前海超高层项目', '(超高层项目)')
    s = s.replace('(十强地产家装方向)', '(地产家装方向)')
    # Full bracket nodes only; unknown or technical qualifiers remain intact.
    def bracket(m):
        b = m[1]
        pure_workplace = re.fullmatch(r'工作地(?:点)?[:：]?[^()]+', b) and not re.search(r'应届|实习|学徒|管培|储备|岗位|工程师|经理|主管|专员|研究员|专业|研发|技术', b)
        if b in BRACKET_EMPLOYERS or b in WORK_PLACES or BRACKET_AD.fullmatch(b) or pure_workplace:
            return ''
        if b == '科达机电2022' and '科达机电2022校园招聘' in raw:
            return ''
        if b == '港企' and '项目稳定+港企不加班' in raw:
            return ''
        if b == '新能源' and '(特变电工新能源)' in raw:
            return ''
        if b == '基金大客户部深圳分区' and '基金大客户部深圳分区' in raw:
            return '(基金大客户)'
        return m[0]
    s = re.sub(r'\(([^()]*)\)', bracket, s)
    # A Japan business-coverage prefix is a place under the user's fixed rule.
    if re.match(r'^对日项目', raw):
        s = re.sub(r'^对日(?=项目)', '', s)
    if '/核心团队/地铁沿线' in raw:
        s = re.sub(r'/核心团队/地铁沿线$', '', s)
    if re.search(r'\d+W-\d+W主管-大团队', raw, re.I):
        s = re.sub(r'(?<=主管)\s*大团队$', '', s)
    if re.fullmatch(r'Java开发\s+区块链', s):
        s = 'Java开发(区块链)'
    return tidy(s) if s != start else start


@lru_cache(maxsize=150000)
def title(raw, t, k, route, child_json):
    before = (t, k, route, child_json)
    raw = base.norm(raw)
    if not TRIGGER.search(raw + '\n' + t) and not re.search(r'工作地|管理培训|装卸/搬运工|QA|teamleader|数据挖掘/模型算法|科技、技术、质量管理岗', raw, re.I):
        return before, ()
    stage = stages_only(raw)
    if stage is not None:
        out = (stage, '', 'X', '[]')
        return (out, ('T1210_CAPTURE_ONLY_PRESENT_STAGE',)) if out != before else (before, ())
    if pure_ad(raw):
        out = ('', '', 'X', '[]')
        return (out, ('T1210_COMPLETE_AD_WITHOUT_OCCUPATION',)) if out != before else (before, ())
    children = json.loads(child_json)
    nt, nk = surface(t, raw), surface(k, raw)
    nc = [surface(c, raw) for c in children]
    ev = ['T1210_COMPLETE_RESIDUE_BOUNDARY'] if (nt, nk, nc) != (t, k, children) else []
    # Recover only known, contiguous raw prefixes; never from source categories.
    for prefix, head in [('细胞治疗', '研发项目'), ('集团', '财务'), ('分公司', '总经理')]:
        if prefix == '集团' and not re.fullmatch(r'财务(?:总监/经理|经理|总监|主管|副总监|副总经理)(?:\([^()]*\))?', nt):
            continue
        if prefix == '分公司' and not re.fullmatch(r'总经理(?:\([^()]*\))?', nt):
            continue
        if raw.startswith(prefix + head) and nt.startswith(head):
            nt = prefix + nt
            nk = prefix + nk if nk.startswith(head) else nk
            nc = [prefix + c if c.startswith(head) else c for c in nc]
            ev.append('T1210_RESTORE_RAW_ROLE_SCOPE')
    if nt == '副驾' and raw.endswith('不开车'):
        nt = '副驾(不开车)'
        nk = '副驾(不开车)' if nk else ''
        ev.append('T1210_RESTORE_RAW_NEGATIVE_TASK_CONSTRAINT')
    if nt == '医药开票员/销售员' and route == 'C':
        nc = ['医药开票员', '医药销售员']
        ev.append('T1210_SHARED_CHILD_SCOPE')
    if re.match(r'^项目成本工程师助理经理(?:\(|$)', raw) and nt == '项目成本工程师/助理经理' and route == 'C':
        nc = ['项目成本工程师', '项目成本助理经理']
        ev.append('T1210_SHARED_CHILD_SCOPE')
    m = re.fullmatch(r'([\u4e00-\u9fff]+)经理/主管\(代建板块\)', nt)
    if m and route == 'C':
        nc = [m[1] + '经理(代建板块)', m[1] + '主管(代建板块)']
        ev.append('T1210_SHARED_CHILD_SCOPE')
    if nt == '装卸/搬运工':
        nk = '装卸搬运工'; route = 'SINGLE'; nc = []
        ev.append('T1210_ESTABLISHED_SYNONYM_STRUCTURE')
    if re.fullmatch(r'封装生产线主管/Assembly Sup', nt, re.I):
        nk = '封装生产线主管'; route = 'SINGLE'; nc = []
        ev.append('T1210_ESTABLISHED_SYNONYM_STRUCTURE')
    if re.fullmatch(r'QA/teamleader英语', nt, re.I):
        nt = 'QA/Team Leader(英语)'; nk = ''; route = 'UNSURE'; nc = []
        ev.append('T1210_PARALLEL_INTERPRETATION_HELD')
    if nt in {'QAQC', '数据挖掘/模型算法', '科技、技术、质量管理岗', '茶学徒/收银'}:
        if nt == 'QAQC': nt = 'QA/QC'
        nk = ''; route = 'UNSURE'; nc = []
        ev.append('T1210_PARALLEL_INTERPRETATION_HELD')
    if nt == '房产精英、学徒' and re.match(r'^招聘多名房产精英、学徒$', raw):
        nt = '房产学徒'; nk = ''; route = 'UNSURE'; nc = []
        ev.append('T1210_BACKGROUND_STAGE_WITHOUT_ROLE')
    m = re.fullmatch(r'业务序列岗\(([^()]+)\)', nt)
    if m and ROLE_END.search(m[1]):
        nt = m[1]; nk = old.old.derive(nt, raw); route = 'SINGLE'; nc = []
        ev.append('T1210_ROLE_INSIDE_JOB_SEQUENCE')
    # Retirement/re-hire is stage, not part of the occupational function.
    if nt.endswith('退休返聘') and nk.endswith('退休返聘'):
        nk = nk[:-4].rstrip(); ev.append('T1210_STAGE_NOT_CORE')
    m = re.fullmatch(r'(.+?)(实习生|学徒)', nt)
    if m and m[1] in ACTIVITIES and not nk and route in {'UNSURE', 'X'}:
        nk = m[1]; route = 'UNSURE'; nc = []
        ev.append('T1210_RESTORE_EXPLICIT_ACTIVITY_CORE')
    if nt in {'仓储储备干部', '管理培训生(业务岗)'}:
        nk = ''; route = 'UNSURE'; nc = []
        ev.append('T1210_BACKGROUND_STAGE_WITHOUT_ROLE')
    if nt == '储备经理人':
        nk = ''; route = 'X'; nc = []; ev.append('T1210_STAGE_ONLY')
    if nt == '主管' and re.search(r'\d+W-\d+W主管-大团队', raw, re.I):
        nk = ''; route = 'UNSURE'; nc = []
    if nt != t and route == 'SINGLE' and not nk:
        # Empty cores are never filled by classification. Only visible job text.
        if ROLE_END.search(nt):
            nk = old.old.derive(nt, raw)
    if nt == 'Android开发工程师' and '/核心团队/地铁沿线' in raw:
        nk = nt; route = 'SINGLE'; nc = []
    if not nt:
        nk = ''; route = 'X'; nc = []
    if route == 'C':
        nk = ''
    output = (nt, nk, route, child_json if nc == children else json.dumps(nc, ensure_ascii=False))
    return (output, tuple(dict.fromkeys(ev))) if output != before else (before, ())


# Directional, bounded function relations.  Parent paths do not erase a
# specific leaf; all independently extracted leaves must satisfy the rule.
SAME = [
    (r'(?:京东|天猫|淘宝)店长', r'网店店长'),
    (r'药品检验员', r'质量检验员'),
    (r'薪酬绩效专员', r'绩效考核'),
    (r'压力容器设计工程师', r'机械工程师'),
    (r'电话销售客服', r'电话销售'),
    (r'医疗器械销售代表(?:\([^()]+\))?', r'医疗器械销售'),
    (r'冲压主管', r'生产主管/组长|生产主管'),
    (r'渠道销售经理(?:\([^()]+\))?', r'渠道销售'),
    (r'设备操作工', r'普工/操作工|操作工'),
    (r'物业保安员', r'保安'),
    (r'(?:国内)?法务专员', r'法务'),
    (r'女装导购(?: 奥莱)?', r'服装销售'),
    (r'电商售前客服专员', r'网络/在线客服|在线客服|网络客服'),
    (r'软件开发员', r'游戏开发'),
    (r'客服\(催收方向\)', r'催收员'),
    (r'机器学习工程师', r'算法工程师'),
    (r'投资顾问', r'证券投资顾问'),
]
DIFFERENT = [
    (r'机械工程师', r'采购经理'),
    (r'(?:防水|工程)销售经理', r'(?:移动)?产品经理'),
    (r'电子开发工程师', r'前端开发'),
    (r'(?:SMB)?销售工程师', r'造价工程师'),
    (r'厂务工程师', r'售前工程师'),
    (r'仪表仪器设计师', r'游戏界面设计师'),
    (r'变电一次设计', r'展览设计'),
    (r'监控与调度工程师', r'认证工程师'),
    (r'学术专员\(护理线\)', r'护士'),
]
SAME = [(re.compile(a, re.I), re.compile(b, re.I)) for a, b in SAME]
DIFFERENT = [(re.compile(a, re.I), re.compile(b, re.I)) for a, b in DIFFERENT]


def relation(a, before, title_changed):
    result = old.old.relation(a, before) if title_changed else list(before)
    if title_changed and before[2] == 'TITLE_NOT_READY' and a[4] and result[0] == 'weak' and a[23] in {'行政/人事', '人事/行政/财务/法务', '咨询/法律/翻译/商标/专利'}:
        result = ['weak', 'candidate_expansion_only', 'BROAD_CATEGORY|OCCUPATION_RELATION_UNCERTAIN']
    if a[14] or a[20] or a[11] == 'malformed' or a[17] == 'malformed' or not a[4] or a[5] in {'C', 'X'}:
        return result
    candidates = [(hp, target) for rules, target in [(SAME, ['usable', 'auxiliary', '']), (DIFFERENT, ['conflict', 'disabled', 'OCCUPATION_CONFLICT'])] for tp, hp in rules if tp.fullmatch(a[4])]
    if not candidates:
        return result
    ls = tuple(x for x in (*semantic_base.leaves(tuple(a[9:15])), *semantic_base.leaves(tuple(a[15:21]))) if x not in base.BROAD_PARENTS | {'物业管理'})
    if not ls:
        return result
    for hp, target in candidates:
        if all(hp.fullmatch(x) for x in ls):
            return target
    return result


def update(before):
    a = list(before)
    a[3:7], events = title(before[2], *before[3:7])
    events = list(events)
    a[25:28] = relation(a, before[25:28], bool(events))
    if a[25:28] != before[25:28]:
        events.append('S1210_INDEPENDENT_LEAF_RELATION')
    if events:
        a[7] = 'SOURCE_GROUNDED_CLOSEOUT_V1210' if a[3:7] != before[3:7] else before[7]
        a[8] = '|'.join(dict.fromkeys([x for x in before[8].split('|') if x] + events))
    a[30] = VERSION
    return a, tuple(events)
