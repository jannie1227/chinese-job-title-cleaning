# 中文职位名称与元数据清洗

独立、可安装的 Python 工具，用于中文职位字符串及招聘类别、初级分类、行业字段的词法预处理。默认运行只需要使用者自己的输入，公开词典随安装包提供；不需要本研究原始数据、私有中间表或 API 密钥。

本仓库只负责职位名称及元数据。岗位描述职责提取见 [chinese-job-description-cleaning](https://github.com/jannie1227/chinese-job-description-cleaning)。

## 安装与直接调用

使用 Python **3.12.x**，运行时只依赖标准库。

```sh
python -m pip install "git+https://github.com/jannie1227/chinese-job-title-cleaning.git@v0.1.0"
```

也可以从 [Releases](https://github.com/jannie1227/chinese-job-title-cleaning/releases) 下载 wheel，使用 `python -m pip install 下载的.whl` 安装。

```python
from chinese_job_title_cleaning import clean_title, clean_record, clean_records

clean_title("急聘JAVA开发工程师(双休)")
# 'Java开发工程师'

clean_record("会计", record_id="SYNTH_001",
             recruitment_category="全职", industry="制造业")
# 返回原字段、清洗字段、分类类型、操作记录、复核原因及规则哈希

clean_records([{"title": "C++工程师"}, {"title": "招聘经理"}, {"title": ""}])
# 保留三条记录，包括空标题；未提供 ID 时按输入顺序生成
```

所有展示文字均为人工构造。接口返回 Python 字符串或可直接 JSON 序列化的字典，不需要先生成研究中的 31 列封存表。

## 普通 CSV

人工 CSV 位于本仓库 `examples/`，下载示例或使用自己的文件路径即可。最少只需一列 `title`。可选提供唯一字符串 ID 和分类字段：

```sh
job-title-clean --input examples/input_synthetic.csv --output cleaned.csv --id-column example_id --recruitment-category-column recruitment_category --initial-category-column initial_category --industry-column industry
```

调用者的中文列名可显式映射：

```sh
job-title-clean --input my_jobs.csv --output my_jobs_cleaned.csv --text-column 招聘岗位 --id-column record_id
```

同一入口也可用 `python -m chinese_job_title_cleaning ...`。CSV / CSV.gz 输入按 UTF-8 读取；输出为 UTF-8 CSV，数组审计字段用 JSON 编码。输出必须是新文件，已存在文件不覆盖。原四项输入和 ID 保留，未声明的额外列不自动透传，方便使用者按 ID 回连自己的原表。

## 两种接口的范围

| 接口 | 输入 | 实现与范围 |
| --- | --- | --- |
| `clean_title` / `clean_record` / `clean_records` | 普通字符串或四字段记录 | 已有公开词法核心 0.4.0、v4 规则快照；格式标准化和明确噪声清理，保护技术符号，分别标准化分类，不推断职业代码 |
| `revise_record` / `job-title-revise` | v1.2.11 的 31 列封存字段 | 原研究 v1.2.12 末轮修订；完整研究未决标记由数据持有者另行提供 |

通用词法清洗与研究终版复现是不同接口。通用接口不声称等价于原研究完整 v1.2.12 结果，也不声称经过总体准确率验收。它没有原研究的私有企业证据和逐原文定案材料；不会为了显示“可调用”而隐式模拟这些材料。

研究修订示例使用人工封存格式输入：

```sh
job-title-revise --input research_input_synthetic.csv --output-dir outputs/research-example
```

原研究完整封存表需要对应本地 `--pending-rules` 配置，私有组合未在仓库中分发。研究字段和质量说明见 [研究接口](docs/RESEARCH.md)，通用函数及字段说明见 [API 文档](docs/API.md)。

## 实现与注释

```text
src/chinese_job_title_cleaning/
  api.py                   # 普通字符串、四字段及批量调用，中文契约注释
  cli.py                   # 普通 CSV 的字段映射、逐条处理与安全写出
  data_rules/              # 随 wheel 安装的公开规则表
  _lexical/                # 已有公开词法函数；包名适配，不读取研究材料
  _frozen_revision.py      # 单独的研究 CSV 修订入口
  _revision/               # 九个原研究修订模块
```

清洗只按明确规则处理。`C++工程师`、`招聘经理` 等人工反例用于检查技术符号和真实职业词不被当作宣传删除；分类字段不会依据标题或行业猜填。保留原值和复核原因，便于调用者逐项检查。

## 验证、数据与许可

```sh
python -m pip install .
python -m unittest discover -s tests -v
python scripts/check_public_files.py
python examples/demo.py
```

测试调用安装后的包，并从临时工作目录运行普通 CSV 入口，检查词典携带、原值保留、空记录、重复 ID、研究接口隔离和输出不覆盖。GitHub Actions 在 Linux、Windows、macOS 上执行同一流程。

展示文件全部是人工示例，仓库不分发原始招聘数据、真实清洗结果、私有配置或企业级输出。输入仅在使用者本地处理。代码为 [MIT](LICENSE)，人工示例和独立规则表为 [CC BY 4.0](LICENSE-DATA)。代码来源及适配哈希见 [source_manifest.json](docs/source_manifest.json)；引用见 [CITATION.cff](CITATION.cff)。
