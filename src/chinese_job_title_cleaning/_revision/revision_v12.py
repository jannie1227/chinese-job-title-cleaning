"""Unified standard v1.2 refinement over sealed v1.1.14.

Only source text, cleaned title and independently parsed category evidence are
inputs. No record IDs, sample orders, review labels or job descriptions.
"""
import json,re
from functools import lru_cache
from . import revision_v118 as base
VERSION='routine_v1.6_standard_v1.2_dev'
def norm(s):return base.norm(s)
def arr(xs):return json.dumps(xs,ensure_ascii=False)
def tidy(s):return re.sub(r'\s+',' ',re.sub(r'\(\s*\)','',s)).strip(' ,;/|—_~')
def core(s):
    s=re.sub(r'\(干部预备岗\)','',s)
    s=re.sub(r'^(?:\d{2,4}届)?(?:本科生|硕士生|博士生)\s*','',s)
    return base.derive_core(s)

# Typed nodes: entire brackets only, never global brand substring deletion.
ENTITY_NODES={'港宏别克高新店','芝麻街英语','罗森','新沂吾悦'}
NOISE_NODES={'高潜力','控股子公司职位','城市不限','易上手','多区域可选','均可安排'}
GEO_NODES={'临港','广佛区域'}
TECH={'hadoop':'Hadoop','bipv':'BIPV','dip':'DIP'}
ACTIVITIES={'机房运维','公共事务','患者教育','模修','综合管理','资产管理'}
PLANS={'春蕾计划','荣耀生','海豚计划','钰星人计划'}
TITLE_TRIGGER=re.compile(r'招聘|市场|招商|管培|实习|学徒|培训生|预备岗|本科生|全职|放射科|飞秒资本|研究团队|业务部门|实验中心|开拓部|奶科院|芝麻街英语|罗森|吾悦|高新店|控股子公司|高潜力|城市不限|易上手|多区域可选|均可安排|临港|广佛|鲁东|对日|上不封顶|外企|驻场|~|方向方向|Hadoop|BIPV|DIP|QAAuditor|EHS专员|运营商|总经理|分公司负责人|组长主管|技术员工程师|工程师/助工|经理/副理|/或|成药营销中心|徐东中商店|华发海滨泳场店|商务兼采购|智能化系统专工|底新|六险一斤',re.I)

def metadata(s,raw):
    originals=re.findall(r'\(([^()]*)\)',raw)
    def bracket(m):
        n=m[1]
        if n in ENTITY_NODES|NOISE_NODES|GEO_NODES:return ''
        if n=='吾悦' and '新沂吾悦' in originals:return ''
        if re.fullmatch(r'运营商\s*20\d{2}',n):return '(运营商)'
        return m[0]
    s=re.sub(r'\(([^()]*)\)',bracket,s)
    # Exact technical token boundaries protect DIPLOMA, BIPVx and unknowns.
    for a,b in TECH.items():s=re.sub(r'(?<![A-Za-z])'+a+r'(?![A-Za-z])',b,s,flags=re.I)
    s=re.sub(r'(?<![A-Za-z])QAAuditor(?![A-Za-z])','QA Auditor',s,flags=re.I)
    s=s.replace('方向方向','方向')
    s=re.sub(r'^驻场(?=安全运维工程师)','',s)
    s=re.sub(r'鲁东(?=地区经理)','',s)
    s=re.sub(r'^对日(?=PM$)','',s)
    s=re.sub(r'[ +/-]*(?:500强外企|上不封顶\s*住宿)$','',s)
    if re.search(r'/六险一斤(?:/|$)',raw):s=re.sub(r'/一斤$','',s)
    # Typed organisations preserve their domain, not their organisational shell.
    m=re.fullmatch(r'高科技组((?:高级|资深)?投资经理)[ -]+飞秒资本',s)
    if m:s=m[1]+'(高科技)'
    m=re.fullmatch(r'(氢能储运)研究团队(.+科研岗)',s)
    if m:s=m[2]+'('+m[1]+')'
    m=re.fullmatch(r'实验中心[ -]+(报告解读师)',s)
    if m:s=m[1]+'(实验)'
    m=re.fullmatch(r'开拓部(业务员)',s)
    if m:s=m[1]+'(开拓)'
    s=re.sub(r'^液奶奶科院(?=畜牧工程师)','液奶',s)
    s=re.sub(r'^来华发海滨泳场店\+(?=卖豪宅$)','',s)
    s=re.sub(r'^徐东中商店招聘(?=珠宝顾问/销售)','',s)
    s=s.replace('(临床线)(成药营销中心)','(临床线、成药营销)')
    return tidy(s)

@lru_cache(maxsize=100000)
def titles(raw,title,c,route,children):
    original=(title,c,route,children)
    if not TITLE_TRIGGER.search(raw+' '+title+' '+c):return original,()
    raw=norm(raw);t=metadata(title,raw);k=metadata(c,raw) if c else '';r=route;ch=children;events=[]
    if (t,k)!=(title,c):events.append('T12_TYPED_SPAN')
    # Restore only an evidenced damaged prefix, never copy arbitrary raw text.
    if re.search(r'招聘(?:与|及)(?:员工关系|培训|人事)',raw) and re.match(r'^(与|及)(员工关系|培训|人事)',t):
        t='招聘'+t;k='招聘'+k if k else k;events.append('T12_OCCUPATION_PROTECTION')
    if '市场' in raw and t.startswith('场') and re.search(r'场(?:专员|主管|经理|总监)',t):
        t='市'+t;k='市'+k if k else k;events.append('T12_OCCUPATION_PROTECTION')
    if '产业招商' in raw and t.startswith('商'):
        t='产业招'+t;k='产业招'+k if k else k;events.append('T12_OCCUPATION_PROTECTION')
    # Division responsibility is a formal organisational scope, not employer.
    if re.search(r'分公司负责人(?:\(|$)',raw) and t=='负责人':t=k='分公司负责人';events.append('T12_FORMAL_SCOPE')
    if re.search(r'分公司总经理',raw) and t.startswith('总经理/副总经理'):
        t='分公司'+t;events.append('T12_FORMAL_SCOPE')
    m=re.fullmatch(r'([A-Z0-9]{2,8})-业务部门-(综合经理)',raw)
    if m:t=k=m[1]+m[2];r='UNSURE';ch='[]';events.append('T12_TYPED_SPAN')
    # Fully recognised ad without occupation, not a global 底新/住宿 deletion.
    if re.fullmatch(r'\(两人间住宿\)\+底新\d+\+上市公司\+师傅带教',raw):
        t=k='';r='X';ch='[]';events.append('T12_NO_OCCUPATION')
    if t=='自动化测试' and '/六险一斤' in raw:r='SINGLE';ch='[]'
    if t=='HRBP' and '500强外企' in raw:r='SINGLE';ch='[]'
    m=re.fullmatch(r'(.+?)\s*EHS专员/EHS专员',t)
    if m:t=k=m[1].rstrip()+'EHS专员';events.append('T12_EXACT_DUPLICATE')

    # Whole stage tokens, not partial substring deletion (本科生 -> 生).
    nt=re.sub(r'\b(未来合伙人)(?=管培生)','',t)
    nt=re.sub(r'^春蕾计划\((管理培训生)\)$',r'\1',nt)
    nt=re.sub(r'^荣耀生\((管培生)\)$',r'\1',nt)
    nt=re.sub(r'管理培训生[ -]+海豚计划(?:\(均可安排\))?','管理培训生',nt)
    nt=re.sub(r'(业务管培生)[ -]+珠宝钰星人计划',r'\1(珠宝)',nt)
    nt=re.sub(r'^管培生生储备干部$','管培生/储备干部',nt)
    nt=re.sub(r'^招聘银行保险部\(985/211院校\)管培生$','银行保险管培生',nt)
    nt=re.sub(r'^(资产管理)部\s*(实习生)$',r'\1\2',nt)
    if nt!=t:t=nt;events.append('T12_COMPLETE_STAGE')
    if t in {'管培生','管理培训生','管培生/储备干部'}:
        k='';r='X';ch='[]'
    elif re.search(r'实习生|学徒|管培生',t) and not base.STAGE_OBJECT.search(t):
        a=tidy(base.STAGE.sub('',t))
        if a in ACTIVITIES:k=a;r='UNSURE';ch='[]'
        elif re.fullmatch(r'市场管培生[ -]+肿瘤线',t):k='市场(肿瘤线)';r='UNSURE';ch='[]'
    if re.match(r'^(?:\d{2,4}届)?(?:本科生|硕士生|博士生)\s+',t):k=core(t)
    if '(干部预备岗)' in t and k:k=core(t)
    if t in {'放射科','法律全职','PM'}:k='';r='UNSURE';ch='[]'
    if t=='商务兼采购':k='';r='UNSURE';ch='[]'

    # Formal role levels are not ordinary seniority synonyms.
    m=re.fullmatch(r'(.+?)(组长)(主管)',t) or re.fullmatch(r'(.+?)(技术员)(工程师)',t)
    if m and not re.search(r'员|经理|主管|总监|工程师|组长',m[1]):
        xs=[m[1]+m[2],m[1]+m[3]];t='/'.join(xs);k='';r='C';ch=arr(xs);events.append('T12_SHARED_STRUCTURE')
    m=re.fullmatch(r'(.+?)经理/副理',t)
    if m:
        xs=[m[1]+'经理',m[1]+'副理'];t='/'.join(xs);k='';r='C';ch=arr(xs);events.append('T12_SHARED_STRUCTURE')
    m=re.fullmatch(r'([^/()]+?工程师)/助工',t)
    if m:k=core(m[1]);r='SINGLE';ch='[]';events.append('T12_GRADE_ALIAS')
    if t.startswith('智能化煤矿技术总监/或售前总监'):
        t=t.replace('/或','/');ch=arr(['智能化煤矿技术总监','智能化煤矿售前总监']);k='';r='C';events.append('T12_SHARED_STRUCTURE')
    if t=='智能化系统专工/工程师':
        # Shared domain is recoverable; role equivalence is not proven.
        r='UNSURE';k='';ch='[]';events.append('T12_UNRESOLVED_STRUCTURE')
    if t=='珠宝顾问/销售' or t.startswith('区域经理/业务经理(临床线、成药营销)'):
        r='UNSURE';k='';ch='[]';events.append('T12_UNRESOLVED_STRUCTURE')
    if r=='C':
        xs=json.loads(ch)
        m=re.fullmatch(r'(.*?)(总经理)/副总经理((?:\([^()]*\))*)',t)
        if m and m[1]:
            qualifiers=re.findall(r'\(([^()]*)\)',m[3])
            if all(q in {'勘察设计行业','通信','集成','供热项目','政府关系/GR','商务开发'} for q in qualifiers):
                xs=[m[1]+'总经理'+m[3],m[1]+'副总经理'+m[3]]
            else:
                # "主持工作" may describe only the deputy. Do not attach it
                # to both roles merely because it is the trailing bracket.
                xs=[m[1]+x if re.match(r'^(?:副)?总经理(?:\(|$)',x) else x for x in xs]
        m=re.fullmatch(r'(市场|产业招商)(专员|经理)/(主管|总监)',t)
        if m:xs=[m[1]+m[2],m[1]+m[3]]
        xs=[metadata(x,raw) for x in xs]
        if xs!=json.loads(ch):ch=arr(xs)
        k=''
    value=(t,k,r,ch)
    if value!=original:
        if k!=c:events.append('T12_CORE_SYNC')
        if (r,ch)!=(route,children):events.append('T12_STRUCTURE_SYNC')
        return value,tuple(dict.fromkeys(events))
    return original,()

# Positive relations require a bounded function pair and every source leaf to
# be compatible. Never select a convenient word from a heterogeneous family.
POSITIVE=[
 (r'(?:输变电)?线路结构工程师',r'线路结构设计'),
 (r'采购项目经理',r'采购经理/采购主管'),
 (r'(?:银行|主任)?软件测试工程师',r'软件测试'),
 (r'环保管理',r'环境管理'),
 (r'(?:IATF\s*)?16949体系工程师',r'质量体系工程师'),
 (r'数据挖掘工程师',r'数据挖掘'),
 (r'财务部主任',r'财务经理'),
 (r'(?:安装)?造价工程师(?:\([^()]*\))?',r'工程造价'),
 (r'过程质量经理',r'质量管理经理/测试经理\(QA/QC经理\)'),
 (r'HRBP',r'人力资源经理/人力资源主管|HRBP'),
 (r'资产管理',r'资产管理'),
]
FUNCTIONS={
 'water_design':r'给排水设计工程师','it_ops':r'运维工程师',
 'financial_sales':r'金融客户经理','duty_manager':r'值班经理',
 'channel_manager':r'餐饮渠道经理','material_formula':r'正极辅材/配方开发工程师',
 'data_dev':r'数据开发','marketing_assistant':r'市场助理','tax_assistant':r'税务助理',
 'pharmacovigilance':r'药物警戒专员','device_rd':r'医疗器械研发',
 'food_process':r'便当/餐食/学生餐项目设备及工艺工程师','pcb_process':r'PCB工艺',
 'clinical_programming':r'临床编程经理SAS programmer','executive_assistant':r'总经理助理',
}
PAIRS={frozenset(x) for x in [('water_design','it_ops'),('financial_sales','duty_manager'),('channel_manager','duty_manager'),('material_formula','data_dev'),('marketing_assistant','tax_assistant'),('pharmacovigilance','device_rd'),('food_process','pcb_process'),('clinical_programming','executive_assistant')]}
POSITIVE=[(re.compile(a,re.I),re.compile(b,re.I)) for a,b in POSITIVE]
FUNCTIONS={k:re.compile(v,re.I) for k,v in FUNCTIONS.items()}
@lru_cache(maxsize=100000)
def relation(c,r,first,second,hint,industry,employment,channel,old,changed):
    if old[0]=='malformed':return old,()
    if not hint:return old,()
    if not c or r in {'C','X'}:
        state=('weak','candidate_expansion_only','TITLE_NOT_READY') if changed else old
        return state,('S12_UPSTREAM_RECOMPUTE',) if state!=old else ()
    leaves=tuple(x for x in (*base.concrete_leaves(first[0],first[3]),*base.concrete_leaves(second[0],second[3])) if x not in base.BROAD_PARENTS)
    if leaves and all(any(a.fullmatch(c) and b.fullmatch(leaf) for a,b in POSITIVE) for leaf in leaves):
        state=('usable','auxiliary','');return state,('S12_BOUNDED_EQUIVALENCE',) if state!=old else ()
    tf={k for k,p in FUNCTIONS.items() if p.fullmatch(c)}
    hf=[{k for k,p in FUNCTIONS.items() if p.fullmatch(x)} for x in leaves]
    if len(tf)==1 and len(hf)==1 and len(hf[0])==1 and frozenset((*tf,*hf[0])) in PAIRS:
        state=('conflict','disabled','OCCUPATION_CONFLICT');return state,('S12_TWO_SPECIFIC_FUNCTIONS',) if state!=old else ()
    if (c,leaves) in {('酒店前台',('前台迎宾',)),('高中数学编辑',('课程设计',))} and old[:2]==('weak','candidate_expansion_only'):
        state=('weak','candidate_expansion_only','OCCUPATION_RELATION_UNCERTAIN');return state,('S12_SPECIFIC_NOT_BROAD',) if state!=old else ()
    if changed:
        state=base.relation(c,r,first,second,hint,industry,employment,channel,old,True,False)
        return state,('S12_UPSTREAM_RECOMPUTE',) if state!=old else ()
    return old,()

def update(before):
    a=list(before);value,e=titles(before[2],*before[3:7]);a[3:7]=value
    state,se=relation(a[4],a[5],tuple(a[9:15]),tuple(a[15:21]),a[23],a[24],a[21],a[22],tuple(before[25:28]),bool(e))
    a[25:28]=state;events=e+se
    if events:
        if e:a[7]='UNIFIED_STANDARD_V12'
        a[8]='|'.join(dict.fromkeys([x for x in before[8].split('|') if x]+list(events)))
    a[30]=VERSION
    return a,events
