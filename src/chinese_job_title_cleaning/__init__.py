"""可直接调用的职位名称和分类元数据清洗；不读取研究私有材料。"""
from .api import TitleCleaner, clean_title, clean_record, clean_records, revise_record

__version__ = '0.1.0'
__all__ = ['TitleCleaner', 'clean_title', 'clean_record', 'clean_records', 'revise_record']
