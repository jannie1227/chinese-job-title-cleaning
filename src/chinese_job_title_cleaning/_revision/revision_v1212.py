"""Development-only whole-span, shared-affix and typed-relation refinement.

Input: sealed v1.2.11 rows. No record identifiers, sample numbers, review labels
or industry enter title rules. Unknown entities/codes stay unchanged. Source
parsing is independent of title; all usable leaves must agree before upgrading.
"""
import json
import re
from functools import lru_cache
from . import revision_v1211 as previous

base = previous.previous.base
VERSION = 'routine_v1.6_standard_v1.2.12_dev'
TECH = {'smt':'SMT','lua':'Lua','bim':'BIM','devops':'DevOps','amoled':'AMOLED','fico':'FICO'}
TOKEN = re.compile(r'(?<![A-Za-z0-9])(?:'+'|'.join(TECH)+r')(?![A-Za-z0-9])', re.I)
DOMAINS = {'动力电池','电子','实施','集成光学','组件制造','肉禽'}
PLACES = {'北京','上海','广州','深圳','成都','宁波','阿联酋'}
ORG_SUFFIX = r'研究院|事业部|制造中心|业务板块|分厂|中心'
STAGE = r'实习生|培训生|管培生|学徒'
ROLE = r'(?:研发|销售|质量|工艺|设备|应用|软件|机械)?工程师|跟单员|操作工|组装工|装配工|客服|HRBP|项目经理|商务经理'
WAGE_TAIL = re.compile(r'(?:\d+(?:\.\d+)?/(?:小时|天)|(?:一月|每月|月薪|月入)\d+(?:\.\d+)?(?:[千万]元?|元|[kK]))+')


def tidy(s):
    return re.sub(r'\s+', ' ', s).strip(' ,;/|—_-')


def tech(s):
    return TOKEN.sub(lambda m: TECH[m[0].lower()], s)


@lru_cache(maxsize=120000)
def surface(raw, value):
    """Change only complete, typed original spans or their attested remnants."""
    if not value: return value
    s = value
    brackets = re.findall(r'\(([^()]*)\)', raw)
    for node in brackets:
        replacement = None
        remnants = {node}
        if re.fullmatch(r'[\u4e00-\u9fff]{2,20}制药厂', node) and not re.search(r'生产|研发|制造|实验|技术|剂型', node[:-3]):
            replacement = ''
        elif re.fullmatch(r'经销商招聘(?:岗位)?|品牌直招[,，、 ]*(?:急|急聘)?', node):
            replacement = ''; remnants.add(node.replace('直招',''))
        elif re.fullmatch(r'(?:需|需要|长期|短期)?出差|驻项目现场', node):
            replacement = ''
        elif any(node in {p+'岗','长期出差'+p,'短期出差'+p,'出差'+p} for p in PLACES):
            replacement = ''; remnants.add('岗')
        elif re.fullmatch(r'[\u4e00-\u9fff]{2,12}\s*-\s*CIS Design House', node, re.I):
            replacement = ''; remnants.add('CIS Design House')
        else:
            m = re.fullmatch(r'(.+?)('+ORG_SUFFIX+r')', node)
            if m and m[1] in DOMAINS: replacement = '('+m[1]+')'
        if replacement is not None:
            for fragment in sorted(remnants, key=len, reverse=True):
                s = s.replace('('+fragment+')', replacement)

    # Restore a dropped domain only when the raw title consists of exactly
    # that role plus a typed department node. Never restore a company name.
    m = re.fullmatch(r'([^()]+)\(([^()]+)('+ORG_SUFFIX+r')\)', raw)
    if m and m[2] in DOMAINS and s in {m[1], base.derive_core(m[1])}:
        s += '('+m[2]+')'

    # Remove redundant organization nouns, retaining technical/product scope
    # and formal group/base/branch management scope.
    for domain in DOMAINS:
        for suffix in ['事业部','业务板块','中心']:
            if domain+suffix in raw and not re.search(re.escape(domain+suffix)+r'(?:主任|负责人|经理|总监)',raw):
                s = s.replace(domain+suffix, domain)
                if suffix == '事业部': s = s.replace(domain+'事业', domain)
    s = re.sub(r'^(营销|销售|研发)中心\1(?=经理|工程师|专员|主管)', r'\1', s)
    if any(p+'办事处' in raw for p in PLACES):
        # A branch director manages that unit: do not erase its formal scope.
        s = re.sub(r'^办事处(?=销售(?:工程师|专员))', '', s)
        if '办事处销售工程师/经理' in raw:
            s = re.sub(r'^办事处(?=销售经理)', '', s)

    # The second, explicit job identifier anchors the preceding fragmented
    # code; arbitrary alphanumeric product/project identifiers are protected.
    m = re.search(r'(经理|主管|专员)([A-Z]{1,3}\d{1,3})-\d{3,7}(?=\(J\d{4,8}\))', raw)
    if m: s = re.sub(re.escape(m[2])+r'$', '', s)

    # Hiring-prefix grammar, not a list of full job titles. It must precede a
    # recognized role, and cannot itself contain a role or technical marker.
    m = re.match(r'^([\u4e00-\u9fff]{2,10})诚聘(?=('+ROLE+r'))', raw)
    if m and not base.ROLE.search(m[1]) and not re.search(r'技术|研发|生产|制造|设备|材料|电池', m[1]):
        if s.startswith(m[1]): s = s[len(m[1]):]

    if re.search(r'[-—]驻外$', raw): s = re.sub(r'[ -]*驻外$', '', s)
    if re.search(r'[-—]驻场大厂[-—](?:双休)?年假\d+天$', raw):
        s = re.sub(r'[ -]*驻场(?:大厂)?[ -]*(?:双休)?年假\d+天$', '', s)
    if raw.endswith('/每周双休'): s = re.sub(r'/每周(?:双休)?$', '', s)
    if re.search(r'\+(?:上市公司\+)?实习盖章\+辅导考证$', raw):
        s = re.sub(r'\++(?:上市公司\+)?实习盖章\+辅导考证$', '', s)
    return tech(tidy(s) if s != value else s)


@lru_cache(maxsize=120000)
def titles(raw, title, core, route, children):
    original = (title,core,route,children)
    raw = base.norm(raw)
    t, c = surface(raw, title), surface(raw, core)
    ch = [surface(raw, x) for x in json.loads(children)]
    events = []
    if (t,c,ch) != (title,core,json.loads(children)): events.append('T1212_ORIGINAL_SPAN_OR_TECH_TOKEN')

    # Complete hourly/monthly wage templates; an unexplained tail prevents
    # recovery, and an existing nonempty UNSURE route is not upgraded.
    m = re.fullmatch(r'((?:组装|装配|包装|操作)工)(.+)', raw)
    if m and WAGE_TAIL.fullmatch(m[2]) and (t != m[1] or c != m[1]):
        t = c = m[1]; ch = []; events.append('T1212_COMPLETE_WAGE_TAIL')

    # Recover a material-qualified role from the raw title, not from industry.
    for material in base.MATERIALS:
        m = re.match(re.escape(material)+r'((?:研发|工艺|技术)?工程师)(?=\(|$)', raw)
        if m and t == m[1] and c == m[1]:
            t = c = material+m[1]; events.append('T1212_MATERIAL_PREFIX_RESCUE')

    # Joined software-role aliases: preserve both original expressions but
    # only collapse the core where the technology token repeats exactly.
    m = re.fullmatch(r'(Java|Python|Go|C\+\+)(软件工程师)\1开发', t, re.I)
    if m and not ch:
        t = m[1]+m[2]+'/'+m[1]+'开发'; c = m[1]+m[2]
        events.append('T1212_SAME_TECH_ALIAS_BOUNDARY')

    # Restore an HR-function prefix and a shared seniority variant, never
    # interpret 招聘专员/招聘经理 as advertising or as one seniority variant.
    m = re.fullmatch(r'(招聘(?:专业师|专员|工程师))/(?:高级|资深)(师|专员|工程师)(?:\(J\d{4,8}\))?', raw)
    if m and (m[1].endswith(m[2]) or (m[2]=='师' and m[1].endswith('师'))):
        et = re.sub(r'\(J\d{4,8}\)$', '', raw)
        if [t,c,route,ch] != [et,m[1],'SINGLE',[]]:
            t,c,route,ch = et,m[1],'SINGLE',[]; events.append('T1212_HR_SENIORITY_ALIAS')

    if route == 'C' and len(ch) == 2:
        # A complete second sales role needs no prefix borrowed from the first.
        m = re.fullmatch(r'((?:区域|大区|地区)销售(?:工程师|经理|专员))/(销售(?:工程师|经理|专员))', t)
        if m and ch[0] == m[1] and ch[1].endswith(m[2]) and ch[1] != m[2]:
            ch[1] = m[2]; events.append('T1212_COMPLETE_SECOND_ROLE')
        # 助理工程师 is a qualification attached to engineer, not a modifier
        # of every following role. Keep the shared technical domain only.
        m = re.fullmatch(r'([^/]+)助理工程师/技术员', t)
        if m and ch == [m[1]+'助理工程师',m[1]+'助理技术员']:
            ch[1] = m[1]+'技术员'; events.append('T1212_GRADE_NOT_SHARED_DOMAIN')

    m = re.fullmatch(r'(养猪|模修|文本标注|技术实施)(技术)?('+STAGE+r')', t)
    if m and not c and route == 'UNSURE':
        c = m[1]+(m[2] or ''); events.append('T1212_EXPLICIT_ACTIVITY_STAGE_CORE')
    if re.fullmatch(r'(?:应往届|应届|往届)(?:毕业生|大学生)(?:储备)?', t) and not c and route == 'UNSURE':
        route = 'X'; events.append('T1212_STAGE_ONLY_NO_OCCUPATION')

    m = re.fullmatch(r'(?:高薪)?诚聘('+ROLE+r')[,，]学历不限[,，]急[!！]?', raw)
    if m and t == m[1]+'/急' and not c and not ch:
        t = c = m[1]; route = 'SINGLE'; events.append('T1212_COMPLETE_RECRUITING_NOISE')
    j = json.dumps(ch,ensure_ascii=False,separators=(',',':')) if ch != json.loads(children) else children
    out = (t,c,route,j)
    return out, tuple(events) if out != original else ()


SHARED_FUNCTIONS = {'产品','品牌','市场','渠道','商务'}
def shared_source(v):
    """Restore all role suffixes solely from the source field, never title."""
    n = base.norm(v[0]).replace('_','/')
    m = re.fullmatch(r'([^<]+?)(专员|助理|经理|主管)', n)
    if not m or '/' not in m[1] or v[2] != 'occupation_taxonomy' or v[5]: return v
    parts = m[1].split('/')
    if not all(p in SHARED_FUNCTIONS for p in parts): return v
    a = list(v); a[3] = '/'.join(p+m[2] for p in parts)
    return tuple(a)


# Typed function signatures are deliberately bounded; no rule says that any
# two different occupational labels must conflict.
SIGNATURES = {
 'customer':r'客服(?:专员)?',
 'electrician':r'(?:售后)?(?:维修|维护)?电工',
 'production_manager':r'(?:生产|车间)(?:经理|主任)',
 'mobile_dev':r'(?:iOS|Android|移动)(?:软件)?开发工程师',
 'erp_dev':r'(?:SAP|ERP)(?:技术)?开发(?:工程师)?',
 'quality_manager':r'(?:精密元件)?(?:质量|品质)(?:部|管理)?(?:经理|主管)',
 'software_dev':r'软件(?:后端|前端)?(?:开发)?工程师',
 'database_admin':r'(?:DBA)?数据库(?:管理员|工程师)',
 'machining_worker':r'(?:机加工|机械加工)操作工',
 'printing_worker':r'印刷操作工',
 'assembly_worker':r'(?:组装|装配)工',
 'reinforcement_worker':r'钢筋工',
 'corporate_culture':r'企业文化(?:工程师|专员)',
 'refrigeration':r'制冷工程师',
 'animal_experiment':r'动物实验(?:技术员|工程师)',
 'telecom_engineer':r'通信技术工程师',
 'ide_tool_dev':r'(?:主任)?IDE工具工程师',
 'network_cabling':r'综合布线工程师',
 'sales_channel':r'(?:通路|渠道)管理经理',
 'network_admin':r'网络管理员',
 'game_dev':r'(?:Lua|C\+\+|Java)?游戏开发(?:工程师)?',
 'game_vfx':r'游戏特效师',
 'quality_inspection':r'质检员(?:\(电子\))?',
 'interior_design':r'室内设计(?:师)?',
 'audit':r'审计(?:专员|员)',
 'academic_research':r'学术研究专员',
}
SIG = {k:re.compile(v,re.I) for k,v in SIGNATURES.items()}
EQUIV = {'customer','electrician','production_manager','mobile_dev','erp_dev','quality_manager','software_dev','database_admin'}
CONFLICT = {frozenset(p) for p in [
 ('machining_worker','printing_worker'),('assembly_worker','reinforcement_worker'),
 ('corporate_culture','refrigeration'),('animal_experiment','telecom_engineer'),
 ('ide_tool_dev','network_cabling'),('sales_channel','network_admin'),
 ('game_dev','game_vfx'),('quality_inspection','interior_design'),
 ('production_manager','quality_manager'),('audit','academic_research'),
]}
SPECIFIC_NODES = {'品牌策划','人事信息系统(HRIS)管理'}


def signature(s):
    return {k for k,p in SIG.items() if p.fullmatch(s)}


def leaves(v):
    n = base.norm(v[0]).replace('_','/')
    if shared_source(v) != v or (re.fullmatch(r'(?:产品|品牌|市场|渠道|商务)(?:/(?:产品|品牌|市场|渠道|商务))+(?:专员|助理|经理|主管)', n)):
        return tuple(shared_source(v)[3].split('/'))
    x = previous.previous.semantic_base.leaves(v)
    # Expand only typed homogeneous aliases; slash in arbitrary categories
    # remains a broad compound, never split to select a convenient token.
    result = []
    for item in x:
        if item == '数据库工程师/管理员': result += ['数据库工程师','数据库管理员']
        elif '/' in item and all(signature(z) for z in item.split('/')): result += item.split('/')
        else: result.append(item)
    return tuple(z for z in result if z not in base.BROAD_PARENTS)


def relationship(a, before, upstream_changed):
    old = tuple(before[25:28])
    if old[0] == 'malformed' or a[14] or a[20] or 'malformed' in {a[11],a[17]}: return old
    state = tuple(previous.previous.relation(a, old, True)) if upstream_changed else old
    if not a[4] or a[5] in {'C','X'} or not a[23]: return state
    ls = (*leaves(tuple(a[9:15])), *leaves(tuple(a[15:21])))
    ts = signature(a[4]); hs = [signature(x) for x in ls]
    if len(ts)==1 and next(iter(ts)) in EQUIV and hs and all(h == ts for h in hs):
        return ('usable','auxiliary','')
    if len(ts)==1 and len(hs)==1 and len(hs[0])==1 and frozenset(ts|hs[0]) in CONFLICT:
        return ('conflict','disabled','OCCUPATION_CONFLICT')
    source_shared = any(shared_source(tuple(before[i:i+6])) != tuple(before[i:i+6]) for i in (9,15))
    if state[:2] == ('weak','candidate_expansion_only') and ls and (all(x in SPECIFIC_NODES for x in ls) or source_shared):
        return ('weak','candidate_expansion_only','OCCUPATION_RELATION_UNCERTAIN')
    return state


def update(before):
    a = list(before)
    values, ev = titles(before[2], *before[3:7]); a[3:7] = values
    events = list(ev)
    for start in (9,15):
        v = shared_source(tuple(before[start:start+6]))
        if v != tuple(before[start:start+6]):
            a[start:start+6] = v; events.append('C1212_INDEPENDENT_SHARED_SUFFIX')
    if a[9:21] != before[9:21]:
        a[23] = base.join_values((a[12],a[18])); a[24] = base.join_values((a[13],a[19]))
    a[25:28] = relationship(a,before,a[3:7]!=before[3:7] or a[9:21]!=before[9:21])
    if a[25:28] != before[25:28]: events.append('S1212_TYPED_RELATION_RECOMPUTE')
    if a[3:7] != before[3:7]: a[7] = 'ORIGINAL_SPAN_AFFIX_V1212'
    if events: a[8] = '|'.join(dict.fromkeys([x for x in before[8].split('|') if x]+events))
    a[30] = VERSION
    return a, tuple(dict.fromkeys(events))
