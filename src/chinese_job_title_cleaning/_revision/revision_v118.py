"""Whole-span refinement of frozen v1.1.7. Pure stdlib, no audit IDs/labels.

Upstream strings are handled before core/structure and relationship derivation.
The sealed baseline is an input, not re-executed through old deletion layers.
"""
import html,json,re,unicodedata
from functools import lru_cache
VERSION='routine_v1.6_standard_v1.1.8_dev'
def norm(s):return unicodedata.normalize('NFKC',html.unescape(s)).strip()
def compact(s):
    s=re.sub(r'\(\s*\)','',s)
    return re.sub(r'\s+',' ',s).strip(' ,;/|—_-')
ROLE=re.compile(r'工程师|设计师|技术员|专员|助理|经理|主管|总监|处长|厂长|负责人|财务BP|班长|组长|值班长|值班员|员|会计|医生|教师|护士|技工|普工|操作工|电工|客服|秘书|顾问|经纪人|代理人|保安|FAE|HRBP|DBA',re.I)
ACTIVITY=re.compile(r'交付|广告投放|网优|生产(?:现场)?管理|生产|屠宰|内勤|业务支持|招聘|安装|维护|维修|设计|研发|开发|运营|营销|销售|采购|培训|化验|测试|工艺|配送|制作|理赔|承做')
GRADE=re.compile(r'初中高级|初中级|中高级|专家级|高级|资深|初级|中级')
STAGE=re.compile(r'应届管培生|管理培训生|储备干部|储备人员|储备生|储备人才|储备岗位|储备岗|培训生|管培生|应届大学生|应届毕业生|应届生|实习生|大学生|实习|兼职|学徒|(?<!存)储备(?!份)')
STAGE_OBJECT=re.compile(r'存储备份|(?:物资|人才|食品|粮食|能源|战略|流动性|现金|资金|外汇|资源|土地|技术)储备|储备粮|实习(?:指导|带教|管理|考核)|(?:实习生|储备生|储备人员)(?:管理|培养|招聘|培训)')
BACKGROUND=re.compile(r'(?:机械|机电|电气|化学|有机化学|技术|自动化|金融|材料|船舶与海洋工程|家禽营养|连锁药店|超市|商场|酒店|门店|仓库|车间|工厂|饰件部门|技术岗位)(?:专业|方向)?')
AD=re.compile(r'(?:待遇好)?有[五六七八九十]险(?:[一二两三]金)?|(?:有无|无需|不限)经验(?:均可|也可)?|到点下班|(?:全国|国内)出差(?=$|[() ,+/])|退休优先|带业绩|(?:补录)(?=$|[() ])|(?:买|交|缴纳)社保[a-z]?(?=$|[()+ ,])|高工价|高薪招聘|高薪|周末休(?:息)?')
META_FULL=re.compile(r'(?:海外|国内|全国)?(?:派遣|外派)|(?:半年|\d+年)(?:到|至|[- ])\d+年[- ]*第三方合同|(?:短期|长期)?第三方合同|.*资深乐迷|到点下班|带业绩|(?:全国|国内)?出差|已毕业学生')
GEO=re.compile(r'Thailand|东南亚|亚太区?|(?<!三)华[东北南中西](?!虎|路)(?:地区|大区|区(?!域))?|日韩|河南|长治(?=$|[() /])|港昌路(?=证券营业部)',re.I)
CODE=re.compile(r'(?<![A-Za-z0-9])(?:J\d{4,7}|HNS\d{3,7}|MJ\d{5,8})(?=$|[() ])')
MATERIALS=('硬质合金','铜线材','电池材料','高分子材料','复合材料','半导体材料','生物材料','陶瓷材料')
DOMAINS=('石油','餐厨','康复','模切','新能源制造业','硅片','总承包')
def explicit_activity(x):
    return bool(x and not BACKGROUND.fullmatch(x) and (ROLE.search(x) or ACTIVITY.search(x)))
def derive_core(text):
    if STAGE_OBJECT.search(text):return text
    s=GRADE.sub('',text)
    s=re.sub(r'\((?:(?:应|往)(?:届)?[、/]?)+(?:大学生|毕业生|生)\)','',s)
    s=re.sub(r'\((?:短期|长期|应届|可|欢迎)?(?:兼职|实习(?:岗位|岗|生)?|应届生|大学生)\)','',s)
    # 管理 is part of the function in 生产现场管理培训生, not a word to erase.
    s=re.sub(r'(生产(?:现场)?)管理培训生',r'\1管理',s)
    s=STAGE.sub('',s)
    s=re.sub(r'[+ ]+(?=\)|$)','',s)
    s=re.sub(r'\((?:短期|长期|此岗位仅限)\)','',s)
    return compact(s)
@lru_cache(maxsize=50000)
def metadata(text,raw):
    x=text
    # Examine the complete original bracket before matching a damaged remnant.
    originals=re.findall(r'\(([^()]*)\)',raw)
    for original in originals:
        if META_FULL.fullmatch(original):
            normalized_original=re.sub(r'[- ]+',' ',original)
            variants={normalized_original,GRADE.sub('',normalized_original),GEO.sub('',normalized_original),GRADE.sub('',GEO.sub('',normalized_original))}
            x=re.sub(r'\(([^()]*)\)',lambda m:'' if m[1] and (re.sub(r'[- ]+',' ',m[1]) in variants or m[1] in original and m[1] not in originals) else m[0],x)
    x=re.sub(r'\([^()]*(?:有限公司|集团[^()]{0,12}院)\)','',x)
    x=re.sub(r'^中建[一二三四五六七八九十]+局[^()]{0,8}公司','',x)
    x=re.sub(r'(?:^|(?<=[ (]))(?:[^\s()]{0,8}大学)?华西医院(?=$|[) ])','',x)
    if '营销总部' in raw:x=x.replace('营销总)','营销)')
    x=re.sub(r'\((?:赴|派驻|驻)(?:阿里|腾讯|华为|网易)\)','',x)
    x=re.sub(r'\((?:保利项目|省直[一二三四五六七八九十]+院)\)','',x)
    x=re.sub(r'\([粤鲁浙苏皖闽赣鄂湘川渝晋冀豫陕甘宁青贵黔滇云桂琼辽吉黑蒙新藏沪京津](?:[,、/ ][粤鲁浙苏皖闽赣鄂湘川渝晋冀豫陕甘宁青贵黔滇云桂琼辽吉黑蒙新藏沪京津])+\)','',x)
    x=GEO.sub('',x)
    x=CODE.sub('',x)
    if re.search(r'实习生\(H0\d\)',raw):x=re.sub(r'\(H0\d\)','',x)
    if re.search(r'销售|经纪人|导购',raw):x=re.sub(r'(?:HNS?|GD|CQ|SZ|SD)\d{3,6}(?=$|\()','',x)
    x=re.sub(r'\+食宿(?=$|[() ])','',x)
    x=re.sub(r'\((?:兼职)?灵活办公不打卡不值班\)','(兼职)' if '兼职灵活办公' in raw else '',x)
    x=re.sub(r'(大学生|应届生)(?:亦可|均可|优先)',r'\1',x)
    if re.search(r'(?:大学生|应届生)(?:亦可|均可|优先)',raw):x=re.sub(r'(?:亦可|均可|优先)$','',x)
    x=re.sub(r'(?<=[员师理管监长])0\d(?=$|\()','',x)
    x=re.sub(r'(?<=[员师理管监长])\d+组(?=$|\()','',x)
    x=AD.sub('',x)
    # Exact raw-span evidence permits short residual removal, never global
    # stop characters 有、各、海 or 招.
    if re.search(r'有[五六七八九十]险',raw):x=re.sub(r'\s+有$','',x)
    if re.search(r'买社保[a-z]$',raw):x=re.sub(r'\+[a-z]$','',x)
    if re.search(r'各\d+名',raw):x=re.sub(r'各(?=\)|$)','',x)
    if re.search(r'有无经验均可',raw):x=re.sub(r'均可$','',x)
    if re.search(r'base地[^ ,()]+',raw,re.I):x=re.sub(r'\s*base地(?=$|[ ,])','',x,flags=re.I)
    x=re.sub(r'\(此岗位仅限(应届生)\)',r'(\1)',x)
    x=re.sub(r'大型集团(?=[^()]+制造业)','',x)
    x=re.sub(r'^(?:某央企|某国企|某上市企业)([^()]{1,8})公司(.+)$',lambda m:m[2]+'('+m[1]+')' if m[1] in DOMAINS else m[0],x)
    x=re.sub(r'^公司(?=.{1,10}部(?:HRBP|人事|财务))','',x)
    x=re.sub(r'^明州康复[ -]+(.+)$',r'\1(康复)',x)
    x=re.sub(r'^(.{1,4})类(?=\1)','',x)
    x=re.sub(r'([一二三四五六七八九十]+)(?=编辑记者$)','',x) if re.search(r'新闻[一二三四五六七八九十]+部',raw) else x
    x=re.sub(r'^(?:如烟大帝辛酸史之)?在.{2,12}当(?=.{2,12}(?:专员|经理|工程师)$)','',x)
    x=re.sub(r'^如烟大帝辛酸史之在.{2,12}当','',x)
    x=re.sub(r'^招(?=(?:安全|质量|检验|销售|采购).{0,8}(?:员|师|经理)$)','',x)
    if '招聘' in raw:
        x=re.sub(r'人事在线招聘(?=普工|操作工|仓管)','',x)
        x=re.sub(r'([师员工生]|兼职)招聘(?=[( ]|$)',r'\1',x)
        x=re.sub(r'招聘(?=普工|操作工|生产储备|经纪人|保险代理人)','',x)
        x=re.sub(r'宝妈$','',x)
    if raw.startswith('世界500强企业'):x=re.sub(r'^企业/','',x)
    x=re.sub(r'^(VR|vr)研究院[/ ]',r'VR',x)
    x=re.sub(r'(?<=客户运营)部(?=经理)','',x)
    for domain in ('硅片','总承包'):
        x=x.replace(domain+'事业部 ',domain).replace(domain+'事业部',domain)
    # Restore a lexical field only when all of it is explicitly in the raw
    # single-role expression, never from employer industry or source taxonomy.
    for material in MATERIALS:
        if re.fullmatch(re.escape(material)+r'(?:高级|资深)?工程师',raw) and x in {'工程师','高级工程师','资深工程师'}:x=raw
    m=re.fullmatch(r'(餐厨|石油|康复)公司[- ]+(.+)',raw)
    if m and x==m[2]:x=m[2]+'('+m[1]+')'
    x=re.sub(r'hrbpleader','HRBP Leader',x,flags=re.I)
    x=re.sub(r'CAENVH','CAE/NVH',x,flags=re.I)
    x=re.sub(r'(?<=客户经理)am$',r'(AM)',x,flags=re.I)
    return compact(x)

@lru_cache(maxsize=40000)
def title(raw,text,core,route,cj):
    original=norm(raw);old=(text,core,route,cj);events=[]
    text=metadata(text,original)
    hr_roles=re.fullmatch(r'招聘(副(?:总监|经理|主管))/((?:副)?(?:经理|总监|主管))',original)
    if hr_roles:
        text=original;core='';route='C';cj=json.dumps(['招聘'+hr_roles[1],'招聘'+hr_roles[2]],ensure_ascii=False)
    # Pure advertisements must be fully evidenced, not inferred by lack of a
    # familiar occupational suffix. Unknown residual titles remain untouched.
    if re.fullmatch(r'J?.{2,8}区高工价月入\d+[Kk]',original) or re.fullmatch(r'\d+号发薪/.{2,25}全家桶随便买\+周末休',original):
        text,core,route,cj='','','X','[]'
    if re.fullmatch(r'(?:急招|高工价|有空调|可借支)+',original):text,core,route,cj='','','X','[]'
    if re.fullmatch(r'(?:保障|薪资|月均|\d+|[+ ]|五险一金|有无经验均可)+',original):text,core,route,cj='','','X','[]'
    if re.fullmatch(r'(?:BYD|比亚迪)高工价\d+(?:\.\d+)?(?:元|一个)?小时',old[0],re.I):text,core,route,cj='','','X','[]'
    if re.fullmatch(r'.{2,25}百货服装品牌招学生兼职',text):
        text,core,route,cj='学生兼职','','X','[]'
    if text=='人才':core,route,cj='','X','[]'
    if re.fullmatch(r'驻(?:海外|外地|国内)干部',text) or re.fullmatch(r'技术青苗\([^()]*方向\)',text):
        core,route,cj='','UNSURE','[]'
    # Job-coded activity in a stage wrapper survives independently of suffixes.
    m=re.fullmatch(r'实习生\((广告AE|[^()]+(?:工程师|专员|助理|设计|开发|投放))\)',text)
    if m:text=m[1]+'实习生';core=m[1];route='UNSURE';cj='[]'
    if re.search(r'\+实习$',text):text=re.sub(r'\+实习$','(实习)',text);route='UNSURE'
    stage=STAGE.search(text) and not STAGE_OBJECT.search(text)
    if stage and route!='C':
        if core:
            core=metadata(core,original)
            proposed_core=derive_core(core)
            if explicit_activity(proposed_core):core=proposed_core
        else:
            candidate=derive_core(text)
            # Backfill only a complete visible functional expression. A stage
            # plus department, education or several alternatives is not a role.
            valid_ending=bool(re.search(r'(?:交付|投放|网优|屠宰|内勤|生产(?:现场)?管理|生产|工程师|技术员|专员|助理|经理|主管|总监|会计|客服|文员|销售员|检验员|经纪人|设计|开发|运营)$',candidate))
            if explicit_activity(candidate) and valid_ending and not re.search(r'[/\\&()、\s\d]|专业|部门|骨干人员|经理人|^人员$|^[市区]|及$|欢迎|亦可|优先|储干|面试|简单|招聘|毕业|精英班',candidate) and not re.search(r'部(?:储备干部|管培生)|总经理.*CEO',original):
                core=candidate
                if route=='X':route='UNSURE'
            elif not candidate and text!=old[0]:core,route,cj='','X','[]'
    elif text!=old[0] and route not in {'C','X'} and old[1]:
        core=derive_core(metadata(old[1],original))
        if core==old[1] and text!=old[0] and old[1]==old[0]:core=derive_core(text)
    # Formal roles separated by whitespace, or unambiguous head repetition.
    m=re.fullmatch(r'(.+?)专员\s+助理',text)
    if m:
        text=m[1]+'专员/'+m[1]+'助理';core='';route='C';cj=json.dumps([m[1]+'专员',m[1]+'助理'],ensure_ascii=False)
    m=re.fullmatch(r'([^/]+?)FAE([^/]+?)FAE',text)
    if m:text=m[1]+'FAE/'+m[2]+'FAE';core='';route='UNSURE';cj='[]'
    if re.fullmatch(r'(?:PMC主管|生产计划主管|物控主管){2,}',text):
        text='/'.join(re.findall(r'PMC主管|生产计划主管|物控主管',text));core='';route='UNSURE';cj='[]'
    m=re.fullmatch(r'(.+?)运维主管值班长值班员',text)
    if m:
        text=m[1]+'运维主管/值班长/值班员';core='';route='C'
        cj=json.dumps([m[1]+x for x in ('运维主管','值班长','值班员')],ensure_ascii=False)
    if text in {'普工/客服','客服/普工'}:core='';route='C';cj=json.dumps(text.split('/'),ensure_ascii=False)
    aliases={'销售代表/业务员':'销售代表','QC/检验员':'检验员'}
    if text in aliases:core=aliases[text];route='SINGLE';cj='[]'
    m=re.fullmatch(r'(.+?)造价/预算工程师',text)
    if m:core=m[1]+'造价工程师';route='SINGLE';cj='[]'
    if re.fullmatch(r'运维工程师&DBA',text):text=text.replace('&','/');core='';route='UNSURE';cj='[]'
    if core and re.search(r'(?:总经理|负责人)\s*储备CEO',text):core='';route='UNSURE';cj='[]'
    if re.fullmatch(r'(?:给排水/暖通设计师|商务/招商经理|商品审核岗/商品基建支持|经纪人/保险代理人)',text):
        core='';route='UNSURE';cj='[]'
    if route=='C':
        children=json.loads(cj);new=[]
        explicit_pair=re.fullmatch(r'(副(?:经理|主管|总监|厂长)|经理)/((?:副)?(?:经理|主管|总监|厂长)|经理助理)',text)
        if explicit_pair:children=list(explicit_pair.groups())
        for child in children:
            proposed=metadata(child,original)
            if child.count('(')==child.count(')') and '/' not in child:proposed=derive_core(proposed)
            if '副副' not in original:proposed=re.sub(r'副副(?=总|经理|主管)','副',proposed)
            new.append(proposed)
        if len(new)==2 and new[0] in {'总裁助理','总经理助理','董事长助理'} and new[1]=='秘书':new[1]=new[0][:-2]+'秘书'
        if len(new)==2 and new[0].endswith('饲养员') and new[1]=='防疫员':new[1]=new[0][:-3]+'防疫员'
        if len(new)==2 and new[0].endswith('英文编辑') and new[1].endswith('记者') and '英文' not in new[1]:
            new[1]=new[0][:-2]+'记者'
        if len(new)>=2 and all(new) and len(new)==len(set(new)):
            if new!=json.loads(cj):cj=json.dumps(new,ensure_ascii=False)
        else:core='';route='UNSURE';cj='[]'
    if text=='测试' and original!=text and re.search(r'(?:全国|国内)出差',original):route='UNSURE'
    if not text:core,route,cj='','X','[]'
    text,core=compact(text),compact(core)
    if text!=old[0]:events.append('V118_COMPLETE_TITLE_SPAN')
    if core!=old[1]:events.append('V118_CORE_STAGE_OR_SCOPE')
    if (route,cj)!=(old[2],old[3]):events.append('V118_OCCUPATION_STRUCTURE')
    return (text,core,route,cj),tuple(events)

@lru_cache(maxsize=12000)
def source(raw,clean,route,occ,industry,unparsed):
    n=norm(raw).replace('_','/');parts=n.split('/')
    # Entire financial-domain list is typed before seeing a title.
    if len(parts)>=2 and set(parts)<={'证券','期货','投资','银行'}:
        return (raw,n,'source_industry','',n,unparsed)
    if len(parts)>=2 and parts[-1].endswith('研发') and all(p.removesuffix('研发') in {'家用电器','数码产品','电子产品','医疗器械'} for p in parts):
        occ='/'.join(p if p.endswith('研发') else p+'研发' for p in parts)
        return (raw,n,'occupation_taxonomy',occ,'',unparsed)
    return raw,clean,route,occ,industry,unparsed
def join_values(values):
    return '/'.join(dict.fromkeys(x for v in values for x in v.split('/') if x))
def head(s):return re.split(r'[( ]',s)[0]
@lru_cache(maxsize=50000)
def concrete_leaves(raw,occupation):
    if not occupation:return ()
    n=norm(raw).replace('_','/')
    leaf=n.split('<',1)[0]
    # Never choose one item in an untyped heterogeneous family to fit a title.
    if '<' in n:return (leaf,) if leaf and leaf.casefold() in occupation.casefold() else ()
    return (occupation,)
POSITIVE=[
 (r'.*配电技工.*',r'电工'),
 (r'物业现场经理.*',r'物业管理经理'),
 (r'.*\(医药代表\).*',r'医药代表'),
 (r'QA(?:[^A-Za-z].*)?',r'QA'),
 (r'(?:IT)?运维岗',r'运维工程师'),
 (r'数字后端(?:设计实现)?工程师',r'数字后端工程师'),
 (r'(?:工业厂房、)?房建项目经理.*',r'工程项目经理'),
 (r'生产班组长.*',r'生产领班/生产组长|生产组长/拉长'),
 (r'客诉专员.*',r'客服专员'),
 (r'.*采购员V?',r'采购专员|采购专员/采购助理'),
 (r'工艺工程师\(精密磨床\)',r'机械工艺工程师'),
 (r'汽车(?:下)?车身设计工程师',r'车身/造型设计'),
]
FUNCTIONS={
 'it':r'IT工程师', 'material':r'材料工程师',
 'quality':r'(?:品质|质量)(?:管理)?(?:经理|主管|总监)',
 'customer':r'客户经理', 'expansion':r'.*门店拓展经理',
 'interaction':r'交互设计经理', 'underwriter':r'保险核保员',
 'insurance_broker':r'保险经纪人', 'wealth':r'.*财富经理岗?',
 'network':r'网络技术经理', 'production_engineer':r'生产工程师',
 'production_worker':r'生产工', 'technical_sales':r'.*销售工程师',
 'mechanical_engineer':r'汽车机械工程师', 'data_operations':r'数据运营经理',
 'database_developer':r'数据库开发工程师', 'sales_director':r'销售总监',
 'creative_director':r'创意总监',
}
CONFLICTS={frozenset(p) for p in [('it','material'),('quality','customer'),('quality','expansion'),('quality','interaction'),('underwriter','insurance_broker'),('wealth','network'),('production_engineer','production_worker'),('technical_sales','mechanical_engineer'),('data_operations','database_developer'),('sales_director','creative_director')]}
POSITIVE=[(re.compile(a,re.I),re.compile(b,re.I)) for a,b in POSITIVE]
FUNCTIONS={k:re.compile(v,re.I) for k,v in FUNCTIONS.items()}
def ftypes(s):return {k for k,p in FUNCTIONS.items() if p.fullmatch(head(s))}
# Independently typed broad parents supply context, not another specific leaf.
BROAD_PARENTS={'生产/制造','生产/工厂','生产/营运','生产/营运/采购/物流','行政/人事','互联网+技术'}
@lru_cache(maxsize=50000)
def relation(core,route,first,second,hint,industry,employment,channel,baseline,upstream_changed,source_changed):
    if baseline[0]=='malformed':return baseline
    if not hint:
        if source_changed and (industry or employment or channel):return 'usable','none',''
        return baseline
    if not core or route in {'C','X'}:return 'weak','candidate_expansion_only','TITLE_NOT_READY'
    leaves=(*concrete_leaves(first[0],first[3]),*concrete_leaves(second[0],second[3]))
    leaves=tuple(x for x in leaves if x not in BROAD_PARENTS)
    # All typed leaves must support an upgrade; conflicting multiple specific
    # sources never disappear by selecting whichever matches the title.
    if leaves:
        positive=lambda leaf: (leaf.casefold()==core.casefold() and bool(ROLE.search(core))) or any(a.fullmatch(core) and b.fullmatch(leaf) for a,b in POSITIVE)
        if all(positive(leaf) for leaf in leaves):return 'usable','auxiliary',''
        tf=ftypes(core);hf=[ftypes(x) for x in leaves]
        if len(leaves)==1 and len(tf)==1 and len(hf[0])==1 and frozenset((*tf,*hf[0])) in CONFLICTS:
            return 'conflict','disabled','OCCUPATION_CONFLICT'
    if core=='设备工程师' and leaves==('机械设备工程师',):
        return 'weak','candidate_expansion_only','OCCUPATION_RELATION_UNCERTAIN'
    if upstream_changed and baseline[2]=='TITLE_NOT_READY':
        broad=bool(re.search(r'互联网\+技术|生产/工厂|销售/客服|人事/财务/行政',hint))
        return 'weak','candidate_expansion_only',('BROAD_CATEGORY|' if broad else '')+'OCCUPATION_RELATION_UNCERTAIN'
    return baseline

def update(before):
    after=list(before)
    title_values,events=title(before[2],*before[3:7])
    after[3:7]=title_values
    a=source(*before[9:15]);b=source(*before[15:21])
    after[9:15]=a;after[15:21]=b
    source_changed=tuple(before[9:15])!=a or tuple(before[15:21])!=b
    if source_changed:
        after[23]=join_values((a[3],b[3]));after[24]=join_values((a[4],b[4]))
        events+=('V118_INDEPENDENT_SOURCE_NODE',)
    state=relation(after[4],after[5],a,b,after[23],after[24],after[21],after[22],tuple(before[25:28]),bool(events),source_changed)
    after[25:28]=state
    if state!=tuple(before[25:28]):events+=('V118_DERIVED_RELATION',)
    if events:
        after[7]='WHOLE_SPAN_CORE_RELATION_V118'
        after[8]='|'.join(dict.fromkeys([x for x in before[8].split('|') if x]+list(events)))
    after[30]=VERSION
    return after,events
