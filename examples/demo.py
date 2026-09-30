"""所有文字均为人工构造；运行时只在本机处理。"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from chinese_job_title_cleaning import clean_title, clean_record

print(clean_title('急聘JAVA开发工程师(双休)'))
print(clean_record('会计', record_id='SYNTH_DEMO', recruitment_category='全职', industry='制造业'))
