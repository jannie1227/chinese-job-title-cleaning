"""Typed qualification repair on sealed v127 rows, without IDs or review inputs.

Exact lexical atoms + bounded composition grammar; unknown text is retained.
This does not assign SOC codes or certify ambiguous titles as occupations.
"""
import json
import re
from functools import lru_cache
from . import revision_v127 as old

VERSION = 'routine_v1.6_standard_v1.2.8_dev'
base = old.base
broken_children = old.broken_children
AD_MARKER = re.compile(r'大平台|全国有岗|外资500强|无需(?:机考|出差|坐班|打卡)|含伙食补助|无水电费|(?:年后|一周内|马上|尽快)到岗')
BACKGROUND = re.compile(r'(?:工程|技术|机电|电气|机械|实验室)(?:实习生|实习)')
ROLE_END = re.compile(r'(?:工程师|设计师|技术员|技术师|技师|专员|经理|主管|总监|顾问|助理|文员|业务员|驾驶员|司机|客服|代表|销售|测试|开发|运营|招聘|会计|出纳|审计师|分析师|保安|保安员|场控|教研|采购|销售支撑|渠道管理|人力资源|生产|工艺|岗)(?:实习生|实习|应届生)?$',re.I)
ROLE_END = re.compile(r'(?:'+ROLE_END.pattern[:-1]+r'|(?:安全管理员|医学信息沟通|数据标注)(?:实习生|实习|应届生)?)$',re.I)
STAGES = {'实习','实习生','应届','应届生','毕业生','兼职','短期用工','假期工','寒假工','可实习','外包','外包岗','派遣','contract'}
EDUCATION = {'统本','学信网统本','统招专科','本科','大专','可小白','可留用','接受大一大二','实习到毕业本科','到毕业本科','今后可根据个人情况定岗','要求有车','第三方用工','固定价','集团本部','上班'}
# Context-only atoms: never delete these from a standalone job/title or technical phrase.
AD_ATOMS = set(old.AD_NODES)|set(old.AD_COMPANIONS)|{
    '大平台','国企','国qi','外企','国企大平台','头部','长期','长期岗位','项目','下午茶','吃住','快晋升','收入高','不出差','带薪休假','出单快','好团队','高温补贴','精准资源','前景优','工作稳定','有出差需求','收入保障','资源多','有发展空间','个人提升','有晋升','易过面','可谈薪','格力','小米科技','福利好','全额','有','生','快速入职','加班','可就近安排','可','岗位','有食堂','不卷假期长','导师带教','专业培训','可放宽学历','薪酬','头部大平台','外资','接受','代招',
}
DOMAINS = {'IVD体外诊断','消费品方向','房产装修','医药','医疗器械','医疗','跨境电商','银行','金融','涂层','自研','核电','总承包项目','互联网'}
AD_ATOMS.update({'无出差','节假日不补班','快速晋升','晋升快','500强','补助','可住宿','晋升好','资源广','发展好','氛围好','高收入','高职级','推荐'})
# These are lexical nodes, not whole-title substitutions. They describe tasks,
# tools, products, negations or experience, not a second complete occupation.
QUALIFIERS = set(old.TECH_QUALIFIERS)|{
    '没有销售性质','维护岗','文职','运营','行政','生产','财税','财税方向','Web','英语','英语口语流利','对接外籍员工','采购管理','人事管理','非管理岗','非财务','非销售','不带外呼','纯接听客服','在线客服','偏运营','偏商务侧支持','含综合事务','销售支持','业务方向','偏技术客服','偏技术支持客服','主管营销','竞品分析','系统设计','规划','概念设计','宣传策划','活动运营','内审','财务审计','IT审计','管理方向','第三方应用','OS','相机','运营商','运营、品牌设计相关','研发','设计','工艺','产品','流程','运营方向','中级','初级','感知','规控','测试工具','底软','数据中心','新能源','通信电源','销售方向','金融项目','技术支持岗位','电商系统类','互联网支付','采购方向','无PLC编程','偏硬件设计选型','会画图','风险管理','风险管理部','培训','活动策划方向','MM模块','ABAP开发','实施运维','财务方向','产品经理方向','后端','前端','电磁兼容工程师','程序员',
}
EXPERIENCE = {'自动化测试','Web','测试','鸿蒙开发','财税领域业务测试','手机终端测试','数据开发','采购、人力管理','定制件制造工艺','抓log'}
ARRANGEMENT = re.compile(r'(?:(?:可|要|要求能)?(?:年后|一周内|马上|尽快)到岗|无需(?:机考|出差|坐班|打卡)|外勤打卡|含伙食(?:补助|补贴)|无水电费|\d+小时(?:两班倒)?|\d+个月项目|春节需留岗)')
PARALLEL = re.compile(r'均有|均在|少量|同时招聘|多岗位|一个偏向|兼(?!容|职)')
# Only isolated location nodes, not substrings (茶山文化研究 is protected).
LOCATIONS = {'赵巷','茶山','江浙沪一带','红花山地铁','天府软件园'}

def eligibility(a):
    t=a[3];out=[]
    if AD_MARKER.search(t):out.append('AD_COMPOSITION')
    if a[5] in {'C','UNSURE'} and '(' in t:out.append('QUALIFIER_OR_JOB')
    if BACKGROUND.fullmatch(t):out.append('BACKGROUND_ONLY')
    return out

def parts(s):
    # Graduation-year slash and technical ++ are not separators.
    s=re.sub(r'(\d{2,4})/(\d{2,4})(?=年毕业)',r'\1§\2',s)
    return [x.strip().replace('§','/') for x in re.split(r'[/、,，;；]|(?<!\+)\+(?!\+)',s) if x.strip()]

def ad_composition(s,raw):
    """Consume the entire known advertisement composition; preserve typed domains.

    No substring deletion on an unrecognized concatenation. Unknown segments
    survive verbatim, even when a nearby advertising marker is recognized.
    """
    special={'内':bool(re.search(r'省内',raw)),'全额':'全额五险' in raw,'有':'有班车' in raw}
    if s in special:return '' if special[s] else s
    if ARRANGEMENT.fullmatch(s):return ''
    if re.fullmatch(r'全国有岗(?:位)?(?:可就近安排)?(?:\s*应届)?',s):return '应届' if '应届' in s else ''
    atoms=sorted(AD_ATOMS|DOMAINS|STAGES|{'外资500强','全国有岗','无需坐班'},key=len,reverse=True)
    todo=s.strip();kept=[];used=False
    while todo:
        todo=todo.lstrip(' +,，/、~～')
        if not todo:break
        m=ARRANGEMENT.match(todo)
        if m:todo=todo[m.end():];used=True;continue
        found=next((x for x in atoms if todo.startswith(x)),None)
        if found is None:return s
        if found in {'有','全额'} and not special[found]:return s
        if found in DOMAINS or found in STAGES:kept.append(found)
        else:used=True
        todo=todo[len(found):]
    return '/'.join(dict.fromkeys(kept)) if used else s

def atom(s,raw,ad_context=False):
    """(clean fragment, core fragment, is non-occupation qualifier)."""
    s=s.strip()
    if not s:return '','',True
    if s in LOCATIONS:return '','',True
    if ad_context:
        updated=ad_composition(s,raw)
        if updated!=s:
            if not updated:return '','',True
            atoms=[atom(x,raw,False) for x in parts(updated)]
            return '/'.join(x[0] for x in atoms if x[0]),'/'.join(x[1] for x in atoms if x[1]),all(x[2] for x in atoms)
    if ARRANGEMENT.fullmatch(s) or s in EDUCATION:return '','',True
    if s in STAGES or re.fullmatch(r'\d{2,4}(?:/\d{2,4})?年毕业',s):return s,'',True
    m=re.fullmatch(r'接受(?:本科)?(应届生|毕业生|寒假工)',s)
    if m:return m[1],'',True
    if s in QUALIFIERS or s in DOMAINS:return s,base.GRADE.sub('',s),True
    m=re.fullmatch(r'(?:有|具备|懂|会|要求有|大专有)?(.+?)(?:工作)?经验(?:最好|就可以)?',s)
    if m and all(re.sub(r'(?:工作)?经验$','',x) in EXPERIENCE for x in re.split('和',m[1])):return s,s,True
    return s,s,False

def qualified(t,raw,ad_context):
    """Return rewritten surface/core and complete-qualifier proof."""
    ok,top,groups=old.structure(t)
    if not ok:return t,t,False
    clean=t;core=t;safe=True;main=old.outside(t)
    for start,end,body in reversed(groups):
        if '(' in body or '[' in body:
            safe=False;continue
        parsed=[atom(x,raw,ad_context) for x in parts(body)]
        # A bare degree/stage is not a job: do not partially strip a degree list
        # such as 应届生(本科/硕士) while having no occupational information.
        if not ROLE_END.search(main) and not ad_context:
            parsed=[(p,p,False) if p in {'本科','大专','统本','学信网统本','统招专科'} else x for p,x in zip(parts(body),parsed)]
        if '/'.join(x[0] for x in parsed if x[0])==main and ROLE_END.search(main):parsed=[('','',True)]
        safe &= all(x[2] for x in parsed)
        # Do not cosmetically replace separators in an unchanged unknown group.
        changed=any(x[0]!=p for x,p in zip(parsed,parts(body)))
        cleanbody='/'.join(x[0] for x in parsed if x[0]) if changed else body
        corebody='/'.join(x[1] for x in parsed if x[1])
        clean=clean[:start]+('('+cleanbody+')' if cleanbody else '')+clean[end+1:]
        core=core[:start]+('('+corebody+')' if corebody else '')+core[end+1:]
    return clean,core,safe and not top

def derive(t,raw):
    _,k,_=qualified(t,raw,bool(AD_MARKER.search(t)))
    # The inherited + trimming must never touch C++ (or other ++ technical tokens).
    k=k.replace('++','\ue001')
    return base.derive_core(k).replace('\ue001','++')

def outer_ad(text,raw):
    """Remove only whole, depth-zero ad nodes; preserve every other span."""
    ok,_,groups=old.structure(text)
    if not ok:return text
    ranges=[]
    for m in re.finditer(r'[^\s/+、,，]+',text):
        if any(start<=m.start()<=end for start,end,_ in groups):continue
        token=m[0]
        if token in DOMAINS or token in STAGES or token in {'薪酬','专业培训','导师带教','项目','生'}:continue
        if ad_composition(token,raw)=='':
            start=m.start();end=m.end()
            # One neighboring delimiter disappears with the advertisement.
            # Never consume ++ from a neighboring technical identifier.
            if start and text[start-1] in ' /、,，':start-=1
            elif start and text[start-1]=='+' and not (start>=2 and text[start-2]=='+'):start-=1
            elif end<len(text) and text[end] in ' /+、,，':end+=1
            ranges.append((start,end))
    for start,end in reversed(ranges):text=text[:start]+text[end:]
    if text.startswith('大平台招聘') and ROLE_END.search(text[len('大平台招聘'):]):text=text[len('大平台招聘'):]
    text=text.strip(' /、,，')
    # Trailing separator after a Chinese role is punctuation, but C+ / C++
    # remain literal technical strings and are never completed or shortened.
    return re.sub(r'(?<![A-Za-z0-9+])\+$','',text)

def pure_peer_ad(raw):
    tokens=[x.strip() for x in raw.split('+')]
    return len(tokens)>=3 and tokens[0] in {'招聘同业','同行业'} and all(x in {'高长底薪','底薪高','高职级','高提点','大平台','资源广','晋升快','上市公司'} for x in tokens[1:])

def alias_safe(t):
    """Only established equivalences, not a broad similarity/substring test."""
    main=old.outside(t);groups=old.structure(t)[2]
    pairs={'EMC工程师':{'电磁兼容工程师'},'软件测试':{'Web测试','中级'},'软件测试工程师':{'Web测试','中级'},'软件设计开发工程师':{'C','Qt','程序员'}}
    return main in pairs and all(p in pairs[main] for _,_,body in groups for p in parts(body))

@lru_cache(maxsize=100000)
def title(raw,t,k,route,child_json):
    original=(t,k,route,child_json);raw=base.norm(raw);children=json.loads(child_json);events=[]
    # A populated UNSURE core can carry an earlier unresolved interpretation.
    # Do not erase that decision just because its qualifiers look familiar.
    if k and route=='UNSURE' and not AD_MARKER.search(t) and not BACKGROUND.fullmatch(t):return original,()
    ad=bool(AD_MARKER.search(t));new,newcore,safe=qualified(t,raw,ad)
    if ad:
        if pure_peer_ad(raw):return ('','','X','[]'),('T128_PURE_AD_NO_OCCUPATION',)
        new=outer_ad(new,raw)
        new=re.sub(r'^无试用期(?=销售)', '',new)
        # Restore the occupational 招聘 token only from the complete raw title.
        if re.match(r'^校园招聘专员\(',raw) and old.outside(new)=='专员':new='校园招聘'+new
    if not k:
        new=re.sub(r'^招(?=(?:通讯)?运营商客服)', '',new)
        new=re.sub(r'(?<=\))总公司(?=人力资源)', '',new)
        new=re.sub(r'^总公司(?=人力资源)', '',new)
    # Only eligible records enter this layer; safe qualification parsing does
    # not authorize arbitrary re-cleaning of every title in the population.
    if new!=t:
        t=new;events.append('T128_TYPED_BRACKET_NOISE')
        if route=='SINGLE':k=derive(t,raw)
        elif k:
            k=qualified(k,raw,ad)[0]
            if ad:k=outer_ad(k,raw)
        children=[qualified(x,raw,ad)[0] for x in children]
        if ad:children=[outer_ad(x,raw) for x in children]
        children=[x for x in children if x]
        if not t:k='';route='X';children=[];events.append('T128_PURE_AD_NO_OCCUPATION')
    ok,top,groups=old.structure(t);main=old.outside(t)
    # A role inside a qualifier is not automatically a second occupation.
    # Conversely, compatible technical labels do not erase a real 兼岗.
    definite=bool(ROLE_END.search(main)) and not PARALLEL.search(main)
    if main in {'综合岗','技术岗','项目岗','工程岗','产品岗','开发'}:definite=False
    if main=='软件工程师' and any('开发' in g[2] and '测试' in g[2] for g in groups):definite=False
    alias=alias_safe(t)
    if route in {'C','UNSURE'} and (not original[1] or route=='C') and ok and not top and definite:
        _,_,safe=qualified(t,raw,ad)
        if (safe and not any(PARALLEL.search(g[2]) for g in groups)) or alias:
            k=derive(t,raw);route='SINGLE';children=[]
            events.append('T128_CONFIRMED_SINGLE_QUALIFIER')
    if ad and route=='SINGLE' and any(re.search(r'多岗位|均在招聘|均有岗位',g[2]) for g in groups):
        k='';route='UNSURE';children=[];events.append('T128_EXPLICIT_MULTIPLE_HOLD')
    if BACKGROUND.fullmatch(t):
        if k or route!='UNSURE' or children:
            k='';route='UNSURE';children=[];events.append('T128_BACKGROUND_NOT_OCCUPATION')
    # Preserve syntax-correct complete multi-job candidates; removing benefits
    # from their fragments is not permission to merge them into a single role.
    output=(t,k,route,child_json if children==json.loads(child_json) else json.dumps(children,ensure_ascii=False))
    return (output,tuple(dict.fromkeys(events))) if output!=original else (original,())

def relation(a,before):
    result=old.previous.relation(a,before,True,False)
    # Only non-specializing constraints allow comparison with the same head.
    # Web/penetration/technical scopes do NOT become synonyms of a broad head.
    neutral={'非销售','非销售岗','无销售','无销售性质','没有销售性质','维护岗','纯接听','不带外呼','不带销售'}
    ok,top,groups=old.structure(a[4])
    if a[5]=='SINGLE' and ok and not top and groups and all(p in neutral for _,_,body in groups for p in parts(body)) and before[0] not in {'conflict','malformed'} and not(a[14] or a[20]):
        leaves=tuple(x for x in (*old.previous.leaves(tuple(a[9:15])),*old.previous.leaves(tuple(a[15:21]))) if x not in base.BROAD_PARENTS)
        if leaves and all(x==old.outside(a[4]) for x in leaves):return ['usable','auxiliary','']
    return result

def update(before):
    a=list(before);events=[]
    if eligibility(before):
        a[3:7],ev=title(before[2],*before[3:7]);events.extend(ev)
        if ev:
            a[25:28]=relation(a,before[25:28])
            if a[25:28]!=before[25:28]:events.append('S128_UPSTREAM_RELATION_RECOMPUTE')
            a[7]='TYPED_QUALIFIER_COMPOSITION_V128'
            a[8]='|'.join(dict.fromkeys([x for x in before[8].split('|') if x]+events))
    a[30]=VERSION
    return a,tuple(dict.fromkeys(events))
