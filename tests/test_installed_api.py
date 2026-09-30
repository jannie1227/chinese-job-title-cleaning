import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from chinese_job_title_cleaning import TitleCleaner, clean_title, clean_record, clean_records, revise_record

ROOT = Path(__file__).resolve().parents[1]


class InstalledTitleAPI(unittest.TestCase):
    def test_bundled_rules_work_without_research_input_or_network(self):
        with patch('socket.create_connection', side_effect=AssertionError('Network not allowed')):
            self.assertEqual(clean_title('急聘JAVA开发工程师(双休)'), 'Java开发工程师')
            self.assertEqual(clean_title('C++工程师'), 'C++工程师')
            self.assertEqual(clean_title('招聘经理'), '招聘经理')
            self.assertEqual(clean_title('学历不限'), '学历不限')

    def test_metadata_values_and_raw_values_are_preserved(self):
        row = clean_record(' 急聘会计 ', record_id='00001', recruitment_category='全职', industry=' 制造业 ')
        self.assertEqual(row['record_id'], '00001')
        self.assertEqual(row['title_raw'], ' 急聘会计 ')
        self.assertEqual(row['industry_raw'], ' 制造业 ')
        self.assertEqual(row['industry_clean'], '制造业')
        self.assertEqual(row['recruitment_category_type'], 'employment_type')
        self.assertEqual(row['initial_category_type'], 'missing')
        self.assertNotIn('soc_code', row)
        json.dumps(row, ensure_ascii=False)

    def test_batch_keeps_empty_and_duplicate_titles(self):
        out = clean_records([{'title':'会计'}, {'title':'会计'}, {'title':''}])
        self.assertEqual(len(out), 3)
        self.assertNotEqual(out[0]['record_id'], out[1]['record_id'])
        self.assertEqual(out[2]['clean_title'], '')
        self.assertIn('empty_title', out[2]['review_reason'])
        with self.assertRaises(ValueError):
            clean_records([{'record_id':'same','title':'会计'}, {'record_id':'same','title':'出纳'}])
        with self.assertRaises(TypeError):
            clean_title(None)

    def test_research_revision_is_separate_and_preserves_four_raw_fields(self):
        with (ROOT / 'research_input_synthetic.csv').open(encoding='utf-8-sig', newline='') as handle:
            before = list(csv.DictReader(handle))[2]
        after = revise_record(before)
        self.assertEqual(after['clean_title'], '组装工')
        self.assertEqual(after['soc_input_route'], 'REVIEW_REQUIRED')
        for name in ['record_id','招聘岗位_raw','招聘类别_raw','初级分类_raw','上市公司行业_raw']:
            self.assertEqual(before[name], after[name])
        with self.assertRaises(ValueError):
            revise_record({'title':'会计'})

    def test_installed_cli_accepts_normal_csv_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'cleaned.csv'
            args = [sys.executable,'-m','chinese_job_title_cleaning','--input',str(ROOT/'examples/input_synthetic.csv'),'--output',str(output),'--id-column','example_id','--recruitment-category-column','recruitment_category','--initial-category-column','initial_category','--industry-column','industry']
            result = subprocess.run(args,cwd=directory,text=True,capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            with output.open(encoding='utf-8-sig',newline='') as handle:
                rows=list(csv.DictReader(handle))
            self.assertEqual(len(rows),4)
            self.assertEqual(rows[0]['clean_title'],'Java开发工程师')
            self.assertEqual(rows[3]['record_id'],'SYNTH_004')
            self.assertEqual(rows[3]['clean_title'],'')
            before=output.read_bytes()
            result=subprocess.run(args,cwd=directory,text=True,capture_output=True,timeout=60)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(output.read_bytes(),before)
            self.assertNotIn('急聘',result.stderr)


if __name__ == '__main__':
    unittest.main()
