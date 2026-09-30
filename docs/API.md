# Python 调用契约

`clean_title(title: str) -> str`：普通标题词法清洗，不需要配置文件。空字符串返回空字符串；非字符串抛出类型错误，不自动猜测缺失值。

`clean_record(title, *, record_id='', recruitment_category='', initial_category='', industry='') -> dict`：处理一条记录，四项原值保留在对应 `*_raw` 字段中，分类各自处理，不跨字段推断。

`clean_records(records) -> list[dict]`：每条输入为包含 `title` 的字典。可选字段与 `clean_record` 一致；缺少 ID 时生成按序 ID，显式 ID 必须非空且唯一。重复标题和空记录保留。

大批量调用可实例化 `TitleCleaner()`，使用 `iter_clean_records` 逐条迭代；默认规则从安装包的 `data_rules` 读取。自建规则目录可通过 `TitleCleaner(rules_dir=...)` 指定，须遵守相同文件和字段契约。

| 返回字段 | 意义 |
| --- | --- |
| `record_id` | 调用者身份键；按字符串保留 |
| `title_raw` / `clean_title` | 原标题与词法清洗值 |
| `recruitment_category_*` / `initial_category_*` | 原值、清洗值及分类类型 |
| `industry_raw` / `industry_clean` | 行业原值与格式标准化值 |
| `removed_terms` | 明确规则删除内容；数组 |
| `location_tag` / `employment_tag` | 规则抽取的标签；数组 |
| `clean_actions` | 处理动作；数组 |
| `clean_status` | unchanged、cleaned 或 review |
| `review_reason` | 需检查的原因；空标题也保留记录 |
| `rule_scope` | public_lexical_v4，避免与研究终版混同 |
| `ruleset_hash` | 已安装词典快照的 SHA-256 |

结果没有 SOC 编码或“已完成职业匹配”标志。词法清洗和真实职业识别的质量需要使用者在自己的数据上另行评估。

`revise_record(record, *, pending=False)` 是独立研究修订接口，要求全部 31 个封存字段。`pending` 来自调用者持有的未决证据，程序不凭标题猜出该状态。普通四字段记录应调用 `clean_record`。
