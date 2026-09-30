"""Bounded attached-advertisement cleanup on v128; no record-level overrides."""
import json,re
from functools import lru_cache
from . import revision_v128 as old

VERSION='routine_v1.6_standard_v1.2.9_dev'
base=old.base
broken_children=old.broken_children
MARKER=re.compile(r'大平台|全国有岗|外资500强|无需(?:机考|出差|坐班|打卡)|(?:年后|一周内|马上|尽快)到岗|愿去福州|长期去福州|中专可投递|入职带教')
EXTRA=re.compile(r'A股上市公司|银行饭碗|招聘同业|同行业\+|退伍特招\+|中海地产宏洋北京')
ROLE=re.compile(r'(?:工程师|设计师|技师|技术员|专员|经理|主管|组长|店长|总监|顾问|助理|文员|经纪人|中介|客服|店员|销售员|维修工|销售|直销|人事|维修|内容审核|地图标注|数据标注|岗|人力资源|技术支持|编辑|Team Assistant)(?:实习生|实习|应届生|管培)?$',re.I)
PREFIX_ROLE=re.compile(r'(?:打字客服|数据标注|地图标注|区域经理|新业务销售|网约车汽车销售|房产|经纪人|贷款专员|车险专员|销售|游泳组长|综合金融主管)')
COMPANY=re.compile(r'(?:美凯龙爱家|我爱我家|万科|百度|Q房网|58|得物(?:app)?)(?:大平台(?:优势|发展)?)',re.I)
ARRANGE=re.compile(r'(?:上班)?无需(?:打卡坐班|坐班打卡|机考|出差|坐班|打卡)|(?:可|要|要求能)?(?:年后|一周内|马上|尽快)到岗|(?:愿去|长期去)福州|节假日不补班')
NOISE={'大平台','大平台发展','上市大平台','国企大平台','大平台很棒','气氛棒','有培训','住宿','有培训住宿','晋升','针对性培训','水产龙头','入职即买','入职带教','中专可投递'}

def eligibility(a):
    out=[]
    if MARKER.search(a[3]):out.append('ATTACHED_AD_OR_ARRANGEMENT')
    if old.AD_MARKER.search(a[2]):out.append('RAW_AD_CONTEXT_PROTECTION')
    if EXTRA.search(a[2]):out.append('RAW_PROVEN_WRAPPER')
    return out

def tidy(s):
    s=re.sub(r'\(\s*\)','',s)
    s=re.sub(r'\s+',' ',s).strip(' /、,，~～&')
    s=re.sub(r'(?<!\+)\+(?!\+)$','',s) if not s.endswith('C+') else s
    s=re.sub(r'^[+/,，、~～\s]+','',s)
    s=re.sub(r'/+','/',s)
    return s.strip(' /、,，~～&')

def whole_ad(s,raw):
    if s in NOISE or COMPANY.fullmatch(s):return True
    if s=='有' and '有底薪' in raw:return True
    if s=='爱家' and '美凯龙爱家' in raw:return True
    if s=='我爱我家' and '大平台' in raw:return True
    if s=='不拖佣金' and '万科' in raw:return True
    if s=='集团' and '集团急招' in raw:return True
    if s=='58爱房' and '58爱房大平台' in raw:return True
    return False

def surface(t,raw):
    """Only known prefix/suffix spans; technical big-platform heads survive."""
    original=t;ad=bool(old.AD_MARKER.search(raw))
    # Source-supported entity aliases are not generic substring dictionaries.
    if ad:
        t=re.sub(r'\(美凯龙爱家\)\s*','',t)
        if '美凯龙爱家' in raw:t=re.sub(r'^爱家\s*','',t)
        if raw.startswith('万科二手房经纪人'):t=re.sub(r'^万科(?=二手房经纪人)','',t)
        if raw.startswith('平安集团讲师'):t=re.sub(r'^集团(?=讲师)','',t)
        if raw.startswith('新东方高中'):t=re.sub(r'^新东方(?=高中)','',t)
        t=re.sub(r'^得物(?=客服专员)','',t)
        t=re.sub(r'^优秀(?=厨师)','',t)
        t=t.replace('+可晋升培养','')
        if re.match(r'^\d+\+天/',raw):t=re.sub(r'^天/','',t)
        if re.search(r'(?:^|/)\d+起(?:/|$)',raw):t=re.sub(r'(^|/)起(?=/|$)',r'\1',t)
        if '福利优' in raw:t=re.sub(r'[、,，]优$','',t)
        if '提供宿舍食堂' in raw:t=re.sub(r'/食堂(?=/|$)','',t)
        if '薪资翻倍' in raw:t=re.sub(r'/翻倍$','',t)
        t=re.sub(r'^接受考研失败\s*','',t)
        t=re.sub(r'^大平台万科(?=房产)','',t)
        t=re.sub(r'^得物(?:app)?大平台(?=客服)','',t,flags=re.I)
        t=re.sub(r'^得物(?:APP)?(?=在线客服)','',t,flags=re.I)
        t=re.sub(r'^58大平台(?:招|聘)(?=新房直销|销售)','',t)
        t=re.sub(r'^优资源大平台(?=综合金融主管)','',t)
        if raw.startswith('平安保险大平台'):t=re.sub(r'^保险大平台(?=办公室客服)','',t)
        # Whole company-plus-benefit nodes must disappear together.
        t=COMPANY.sub(lambda m:'' if (m.start()==0 or t[m.start()-1] in ' /+、,，(') and (m.end()==len(t) or t[m.end()] in ' /+、,，)') else m[0],t)
        t=re.sub(r'(^|[ /+、,，])大平台(?:高发展|发展)?(?=.+)',lambda m:m[1] if PREFIX_ROLE.match(t[m.end():]) else m[0],t)
        t=re.sub(r'^全国有岗(?=农业数字化营销管培)','',t)
        t=re.sub(r'^外资500强(?=Team Assistant\b)','',t)
        t=re.sub(r'^加入我爱我家大平台高收入$','',t)
        t=re.sub(r'^大平台有培训(?:住宿)?$','',t)
        # At a complete role/domain boundary, this is employer promotion.
        t=re.sub(r'(?:国企)?大平台(?:很棒|优势|发展)?(?=$|[ +/,，、)])',lambda m:'' if ROLE.search(t[:m.start()].rstrip()) or re.search(r'(?:房产装修|智慧教育|\))$',t[:m.start()].rstrip()) else m[0],t)
        t=re.sub(r'职等你站$','',t) if re.search(r'销售职等你站$',t) else t
        t=re.sub(r'培训大平台$','',t) if re.search(r'店长培训大平台$',t) else t
        t=re.sub(r'^四千(?=人事)', '',t) if re.search(r'^四千人事.*无需',raw) else t
        t=re.sub(r'^\d+-\d+(?=权证专员)','',t) if re.match(r'^\d+-\d+诚聘',raw) else t
    # Complete working-arrangement clauses do not become occupation words.
    t=ARRANGE.sub('',t)
    t=t.replace('中专可投递','').replace('入职带教','')
    if 'A股上市公司' in raw and raw.count('A股')==raw.count('A股上市公司'):
        t=re.sub(r'A股(?:旗下品牌)?','',t)
        t=re.sub(r'^500强企业[+ ]*','',t)
        t=re.sub(r'^高成长[ ]*(?=管培生)','',t)
        t=re.sub(r'^[,， ]*招(?=广告销售)','',t)
        t=re.sub(r'(?<=体检)精英$','',t)
    if raw.startswith('银行饭碗') and '电话客服' in raw:
        t=re.sub(r'^银行饭碗\s*','',t)
        t=re.sub(r'\s*只招[一二三四五六七八九十两\d]+人$','',t)
    if raw.startswith('同行业+') and ROLE.search(t):
        t=re.sub(r'^同行业[+,， ]*','',t)
        t=t.replace('弹性工作时间+','')
    t=t.replace('(中海地产宏洋北京)','')
    # Work inside brackets too, preserving all unrecognized qualifiers.
    ok,_,groups=old.old.structure(t)
    if ok:
        for start,end,body in reversed(groups):
            if '(' in body:continue
            tokens=re.split(r'\s+|[/、,，]|(?<!\+)\+(?!\+)',body)
            kept=[x for x in tokens if x and not whole_ad(x,raw)]
            if ad:kept=[x for x in kept if x not in {'集团本部','外资500强','接受大一大二'}]
            if kept!=tokens:
                body='/'.join(kept);t=t[:start]+('('+body+')' if body else '')+t[end+1:]
    # Remove complete top-level benefit nodes, not professional 培训 or 薪酬.
    ok,_,groups=old.old.structure(t)
    if ok:
        ranges=[]
        for m in re.finditer(r'[^\s/+、,，~～]+',t):
            if any(start<=m.start()<=end for start,end,_ in groups):continue
            if whole_ad(m[0],raw):
                start,end=m.span()
                if start and t[start-1] in ' /+、,，~～' and not t[max(0,start-2):start]=='++':start-=1
                elif end<len(t) and t[end] in ' /+、,，~～':end+=1
                ranges.append((start,end))
        for start,end in reversed(ranges):t=t[:start]+t[end:]
    t=tidy(t)
    # Do not normalize unknown technical punctuation without actual cleanup.
    return t if t!=tidy(original) else original

def pure_ad(raw):
    raw=base.norm(raw)
    if re.fullmatch(r'[\[(【《]?银行饭碗[\])】》]?(?:双休)?均薪\d+不加班\+五险一金',raw):return True
    if re.fullmatch(r'[\[(【《]?银行饭碗[\])】》]?月入\d+[kK]\+五险一金\+周末休',raw):return True
    if re.fullmatch(r'A股上市公司\s*\d+年国民品牌\s*岗位虚位以待\s*欢迎你的加入',raw):return True
    parts=raw.split('+')
    identities={'招聘同业','同行业','房产同行业','退伍特招','房产行业','招聘房产同业','高薪聘同业','优先同业🏠'}
    if len(parts)<2 or not any(p in identities for p in parts):return False
    pattern=r'(?:(?:高长(?:无责)?底薪|底薪高|高职级|高提点|大平台|资源广|资源多|有保障|晋升快|上市公司|上市|收入没有上限|高底薪|[l1]?核心位置老店面|热门成交区|底薪(?:最高)?\d+(?:万|千)?))+'
    return all(p in identities or re.fullmatch(pattern,p) for p in parts)

def single_safe(t):
    ok,top,groups=old.old.structure(t)
    main=old.old.outside(t)
    if not ok or top or re.search(r'(?<!\+)\+(?!\+)|~',main):return False
    if not ROLE.search(main) or main in {'工程岗','技术岗','综合岗','项目岗'}:return False
    return all(all(old.atom(p,'',False)[2] for p in old.parts(body)) for _,_,body in groups)

@lru_cache(maxsize=100000)
def title(raw,t,k,route,child_json):
    before=(t,k,route,child_json);raw=base.norm(raw);ev=[]
    if pure_ad(raw):
        final=('','','X','[]')
        return (final,('T129_PURE_WRAPPER_NO_ROLE',)) if final!=before else (before,())
    nt=surface(t,raw)
    if nt==t:return before,()
    ev.append('T129_ATTACHED_WRAPPER_BOUNDARY')
    children=json.loads(child_json)
    children=[surface(c,raw) for c in children];children=list(dict.fromkeys(c for c in children if c))
    nk=surface(k,raw) if k else ''
    if not nt:nk='';route='X';children=[]
    elif route=='C':
        if len(children)<2:
            route='SINGLE' if single_safe(nt) else 'UNSURE';nk=old.derive(nt,raw) if route=='SINGLE' else '';children=[]
    elif route=='SINGLE':nk=old.derive(nt,raw)
    elif route=='UNSURE' and single_safe(nt):
        # Cleanup must remove the actual source of ambiguity, not merely format.
        if old.AD_MARKER.search(raw) or EXTRA.search(raw):
            nk=old.derive(nt,raw);route='SINGLE';children=[];ev.append('T129_ROLE_AFTER_WRAPPER_REMOVAL')
    if nt and re.search(r'管培$',nt):
        nk=re.sub(r'管培$','',nt);route='UNSURE';children=[]
    if nt in {'实习','实习生','应届生','管培生','储备干部'}:
        nk='';route='UNSURE';children=[]
    # Never join parallel role names just because their advertisements vanished.
    if route=='SINGLE' and old.old.structure(nt)[1]:
        nk='';route='UNSURE';children=[];ev.append('T129_PARALLEL_REQUIRES_INTERPRETATION')
    result=(nt,nk,route,json.dumps(children,ensure_ascii=False))
    return (result,tuple(ev)) if result!=before else (before,())

def update(before):
    a=list(before);ev=[]
    if eligibility(before):
        a[3:7],events=title(before[2],*before[3:7]);ev.extend(events)
        if events:
            a[25:28]=old.relation(a,before[25:28])
            if a[25:28]!=before[25:28]:ev.append('S129_UPSTREAM_RELATION_RECOMPUTE')
            a[7]='ATTACHED_AD_BOUNDARY_V129'
            a[8]='|'.join(dict.fromkeys([x for x in before[8].split('|') if x]+ev))
    a[30]=VERSION
    return a,tuple(ev)
