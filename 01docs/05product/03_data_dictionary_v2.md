# Power Up Picture Book Forge — Data Dictionary

> 文件路径建议：`01docs/05product/03_data_dictionary_v2.md`  
> 文档角色：定义 Power Up Picture Book Forge（Power Up 绘编）Demo 的核心数据实体、字段、关系、状态与一致性约束。  
> 上位文档：`01_product_workflow_v2.md`  
> 数据来源映射：`02_data_mapping_v2.md`

---

# 1. 文档目的

本文件回答：

1. SQLite 中需要哪些核心实体；
2. 每个实体存什么；
3. 哪些属于静态参考数据，哪些属于教师运行时数据；
4. Proposal、Draft、Final、词汇角色、复现记录如何关联；
5. Final / 撤销 Final 时如何保证历史冲突与复现统计不被算乱；
6. 哪些字段是系统事实，哪些字段是教师确认结果，哪些只是 AI 建议；
7. 哪些数据允许 LLM 读取，哪些数据只能通过 Workflow / Service 间接访问。

本文件不定义：

- Prompt 的具体文本；
- Validation 的 Pass / Warning 阈值细节；
- RAG chunking / embedding 规则；
- UI 视觉布局。

这些分别由后续文档定义。

---

# 2. 数据层总体结构

建议将数据分成三层：

```text
A. Static Reference Data
   原始教研资料构建出的权威参考数据

B. Runtime / Project Data
   教师使用产品时产生的 Proposal、Draft、选择、编辑和确认

C. Final / Historical Data
   已正式定稿并参与历史冲突、动态词库和复现统计的数据
```

建议 SQLite 中逻辑分区如下：

```text
REFERENCE
├── source_documents
├── source_conflicts
├── product_overrides
├── levels
├── level_rules
├── book_types
├── topics
├── textbook_words
├── textbook_structures
└── textbook_examples

RUNTIME
├── projects
├── project_overrides
├── proposals
├── proposal_vocabulary
├── proposal_patterns
├── draft_versions
├── draft_pages
├── draft_sentences
├── planned_vocabulary
├── draft_vocab_observations
├── draft_pattern_observations
├── vocabulary_confirmations
├── validation_runs
├── validation_issues
└── key_visuals

FINAL / HISTORY
├── final_books
├── final_book_vocabulary
├── final_book_patterns
├── recurrence_events
├── finalization_events
└── imported_historical_books
```

实际实现可合并部分表，但必须保留这些逻辑边界。

---

# 3. 命名与数据原则

## 3.1 ID

所有运行时实体使用稳定 ID，例如：

```text
project_id
proposal_id
draft_id
book_id
validation_run_id
```

建议使用：

- UUID；
- 或不可重复的稳定字符串 ID。

不得依赖 UI 排序号作为数据库主键。

---

## 3.2 时间字段

动态实体统一保留：

```text
created_at
updated_at
```

Final 相关实体额外保留：

```text
finalized_at
reopened_at
```

建议使用 ISO 8601 时间。

---

## 3.3 状态字段

状态必须使用 canonical enum，而不是自由文本。

例如：

```text
PROPOSAL
SELECTED_PROPOSAL
DRAFT
VOCAB_CONFIRMED
FINAL
REOPENED
ARCHIVED
```

---

## 3.4 原始值与标准值分离

凡涉及规范化，不覆盖原值。

例如：

```text
raw_label = 文化对比型
canonical_label = 跨学科提升
```

词汇同理：

```text
raw_form = children
lemma = child
```

---

# 4. Static Reference Data

---

# 5. `source_documents`

记录原始教研资料来源。

## 5.1 用途

支持：

- 数据溯源；
- 自动重建；
- 冲突定位；
- 判断某条结构化数据来自哪份文件。

## 5.2 建议字段

| 字段 | 类型概念 | 必需 | 说明 |
|---|---|---:|---|
| `source_document_id` | text/id | 是 | 主键 |
| `source_name` | text | 是 | 如“03语言项目收录标准” |
| `source_path` | text | 是 | `docs/...` 相对路径 |
| `source_type` | enum | 是 | docx / xlsx / md / other |
| `source_hash` | text | 建议 | 用于判断源文件是否变化 |
| `source_version` | text | 否 | 若人工有版本号则保存 |
| `parsed_at` | datetime | 是 | 最近解析时间 |
| `active` | bool | 是 | 当前是否为有效来源 |

---

# 6. `source_conflicts`

记录原始资料之间已发现的规则冲突。

## 6.1 示例

Level 2 核心词单篇复现：

```text
03语言项目收录标准（表格） = 3–5 次
03语言项目收录标准（正文） = ≥3 次
```

当前产品决定：

```text
3–5 次为建议目标，不是 Final 硬约束
```

（注：Power Up 2 源中 02分级标准 与 03语言项目收录标准 的单篇词数一致为 120–200，旧版篇幅冲突已消失。）

## 6.2 建议字段

| 字段 | 说明 |
|---|---|
| `conflict_id` | 主键 |
| `rule_key` | 如 `level2.book_word_count` |
| `source_document_id` | 来源 |
| `source_section` | 来源章节 |
| `raw_value` | 原始值 |
| `normalized_value` | 可选标准化表示 |
| `resolution_status` | unresolved / resolved |
| `resolution_note` | 人工决定说明 |
| `effective_override_id` | 若有，对应 product override |

原则：

> 不允许用 Product Override 覆盖后删除原始冲突记录。

---

# 7. `product_overrides`

记录已经由产品负责人明确决定的执行值。

## 7.1 当前至少包含

```text
book_type.cross_curricular = 跨学科提升
level2.book_word_count_min = 120
level2.book_word_count_max = 200
vocabulary_detection_v1 = lemma + manual review warning
proposal_to_fulltext.requires_human_selection = true
formal_vocabulary_write.requires_final = true
```

## 7.2 建议字段

| 字段 | 说明 |
|---|---|
| `override_id` | 主键 |
| `rule_key` | 稳定唯一 key |
| `effective_value_json` | 当前有效值 |
| `reason` | 决策原因 |
| `decided_at` | 决策时间 |
| `active` | 当前是否生效 |

---

# 8. `levels`

存分级基本信息。

## 8.1 建议字段

| 字段 | 说明 |
|---|---|
| `level_id` | 1–6 |
| `level_name` | Level 1 等 |
| `stage_positioning` | 阶段定位 |
| `active_in_demo` | Demo 是否启用 |

当前：

```text
Level 2 active_in_demo = true
```

---

# 9. `level_rules`

存可结构化的 Level 规则。

## 9.1 建议字段

| 字段 | 说明 |
|---|---|
| `level_rule_id` | 主键 |
| `level_id` | 外键 |
| `rule_key` | 如 `sentence_max_words` |
| `raw_value` | 原始值 |
| `effective_value` | 产品当前执行值 |
| `value_type` | int / range / float / text / json |
| `rule_strength` | hard / target / soft / warning |
| `source_document_id` | 来源 |
| `source_section` | 来源章节 |
| `note` | 解释 |

## 9.2 为什么采用 Key-Value 结构

Level 1–6 的规则维度可能不断变化。

与其一次建立几十个固定列，更适合：

```text
level_id + rule_key + effective_value
```

对 Demo 更灵活。

如果后期规则稳定，可再转为强类型配置对象。

---

# 10. `book_types`

定义绘本分类。

## 10.1 Canonical Values

```text
TEXTBOOK_SYNC
THEME_EXTENSION
CROSS_CURRICULAR
```

显示：

```text
教材衔接
主题拓展
跨学科提升
```

## 10.2 建议字段

| 字段 | 说明 |
|---|---|
| `book_type_id` | 主键 |
| `code` | 稳定英文 code |
| `display_name_zh` | 中文显示 |
| `core_positioning` | 核心定位 |
| `relationship_to_textbook` | 与教材关系 |
| `usage_scenario` | 使用场景 |
| `active` | 是否启用 |

---

# 11. `topics`

Level 2 Topic 主表。

## 11.1 建议字段

| 字段 | 说明 |
|---|---|
| `topic_id` | 稳定 ID |
| `level_id` | 当前为 2 |
| `semester` | 固定 "Power Up 2"（不分上下册，字段保留兼容） |
| `unit_number` | 1–9 |
| `topic_number` | 1–9 |
| `unit_title` | 教材 Unit Title |
| `theme` | 教材 Theme |
| `essential_question` | Essential Question |
| `grammar_text` | Grammar |
| `cross_curricular_text` | Cross-curricular |
| `literature_text` | Literature |
| `source_document_id` | 来源 |
| `active` | 是否启用 |

## 11.2 唯一约束

至少：

```text
UNIQUE(level_id, topic_number)
```

以及：

```text
UNIQUE(level_id, semester, unit_number)
```

避免 Topic 映射重复。

---

# 12. `textbook_words`

保存 Topic 对应教材词汇 / 语言项目。

## 12.1 建议字段

| 字段 | 说明 |
|---|---|
| `textbook_word_id` | 主键 |
| `topic_id` | 外键 |
| `raw_entry` | 教材原始写法 |
| `normalized_entry` | 用于查询的标准写法 |
| `entry_type` | word / phrase / expression |
| `sequence_no` | 原始顺序 |
| `source_document_id` | 来源 |

原则：

> `textbook_words` 不等于 `final core words`。

---

# 13. `textbook_structures`

保存教材 Structure。

## 13.1 建议字段

| 字段 | 说明 |
|---|---|
| `textbook_structure_id` | 主键 |
| `topic_id` | 外键 |
| `raw_structure` | 原始教材结构 |
| `normalized_pattern` | 可空；后续人工/系统确认 |
| `sequence_no` | 原始顺序 |
| `source_document_id` | 来源 |

ETL 阶段不得自行把原句改写为“标准句型”。

---

# 14. `textbook_examples`

保存教材额外语句、Revision、Songs。

## 14.1 建议字段

| 字段 | 说明 |
|---|---|
| `example_id` | 主键 |
| `topic_id` | 可空 |
| `raw_sentence` | 原始句子 |
| `source_section` | topic / revision / songs |
| `sequence_no` | 顺序 |
| `verification_status` | verified / pending / rejected |
| `source_document_id` | 来源 |
| `note` | 人工备注 |

## 14.2 当前 Verification 约定

暂按：

```text
（当前 Power Up 2 源无教材额外例句，本表为空；
后续人工补充时按 verified / pending 记录核验状态。）
```

直到教研人工进一步核验。

---

# 15.（已移除）`curriculum_entries` / `curriculum_variants`

Power Up 2 版本不再包含独立课标词汇源，这两张表已从 schema 中移除。

词汇来源判定改为 Power Up 2 教材全册 `textbook_words` 范围：

- 本单元命中 → `TEXTBOOK`；
- 其他单元命中 → `TEXTBOOK_SCOPE`；
- 未命中 → `UNRESOLVED`（人工复核，不自动判为不允许）。

教材词表中的斜杠变体（如 `leaf/leaves`、`clean/brush your teeth`）在查询时展开为
可替代形式；提取时保留原文 `raw_entry` 用于溯源。

---


# 17. Runtime / Project Data

---

# 18. `projects`

表示教师针对某一 Topic 开展的一次绘本生产工作。

一个 Project 可以包含：

- 多个 Proposal；
- 多个 Draft version；
- 最终 0 或 1 个当前有效 Final。

## 18.1 建议字段

| 字段 | 说明 |
|---|---|
| `project_id` | 主键 |
| `topic_id` | 外键 |
| `working_title` | 可空 |
| `status` | ACTIVE / FINAL / REOPENED / ARCHIVED |
| `selected_proposal_id` | 可空 |
| `current_draft_id` | 可空 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

## 18.2 关键原则

如果同一个 Topic 要做 5 本绘本：

> 应创建 5 个 Project。

不要把“一个 Topic 的所有绘本”塞进一个 Project。

这样 Final、书号和词汇角色才不会混淆。

若教师一次选择多个 Proposal：

> 系统自动拆分为多个独立 Project，每个 Proposal 对应一个 Project。

UI 不需要使用工程术语 “fork”。


---

# 19. `project_overrides`

保存教师对当前 Topic 教材输入的临时修改。

例如：

- 删除某教材词；
- 加入一个教师希望使用的词；
- 增加一个句型；
- 添加创作要求。

## 19.1 建议字段

| 字段 | 说明 |
|---|---|
| `project_override_id` | 主键 |
| `project_id` | 外键 |
| `override_type` | add_word / remove_word / add_structure / remove_structure / creative_instruction |
| `raw_value` | 教师输入 |
| `created_at` | 时间 |
| `active` | 是否当前有效 |

原则：

> 不覆盖静态教材表。

---

# 20. `proposals`

保存 AI 生成或教师编辑后的 Proposal。

## 20.1 建议字段

| 字段 | 说明 |
|---|---|
| `proposal_id` | 主键 |
| `project_id` | 外键 |
| `proposal_batch_id` | 同一轮生成批次 |
| `proposal_index` | UI排序 |
| `title` | Proposal 标题 |
| `entry_point_cn` | 中文切入点 |
| `storyline` | 初步完整故事逻辑 |
| `book_type_id` | 教材衔接/主题拓展/跨学科提升 |
| `plot_structure` | 情节结构 |
| `potential_issues` | 潜在问题 |
| `creative_highlight` | 可空 |
| `status` | GENERATED / SELECTED / REJECTED |
| `created_at` | 时间 |
| `updated_at` | 时间 |

---

# 21. `proposal_vocabulary`

保存 Proposal 阶段的预测词。

## 21.1 建议字段

| 字段 | 说明 |
|---|---|
| `proposal_vocab_id` | 主键 |
| `proposal_id` | 外键 |
| `raw_form` | Proposal 输出 |
| `normalized_form` | 标准化形式 |
| `lemma` | 可空 / NLP生成 |
| `predicted_role` | CORE / EXTENSION |
| `source_lookup_status` | textbook / textbook_scope / unresolved |
| `manual_review_required` | bool |
| `sequence_no` | 顺序 |

注意：

> Proposal vocabulary 是预测值，不进入正式动态词库。

---

# 22. `proposal_patterns`

保存 Proposal 阶段预测核心句型。

## 22.1 建议字段

| 字段 | 说明 |
|---|---|
| `proposal_pattern_id` | 主键 |
| `proposal_id` | 外键 |
| `raw_pattern` | AI / 教师提供的句型 |
| `normalized_pattern` | 可空 |
| `source_relation` | textbook / derived / teacher_added / unresolved |
| `sequence_no` | 顺序 |

---

# 23. `draft_versions`

每次完整正文版本对应一条 Draft Version。

## 23.1 建议字段

| 字段 | 说明 |
|---|---|
| `draft_id` | 主键 |
| `project_id` | 外键 |
| `proposal_id` | 外键 |
| `parent_draft_id` | 可空；用于重写/版本谱系 |
| `version_number` | 版本号 |
| `generation_orientation` | STORY / LANGUAGE / BALANCED |
| `page_count_target` | 8 / 12 |
| `word_count_target_min` | 当前 120 |
| `word_count_target_max` | 当前 200 |
| `status` | DRAFT / VOCAB_CONFIRMED / SUPERSEDED |
| `created_at` | 时间 |
| `updated_at` | 时间 |

## 23.2 为什么必须保留 `parent_draft_id`

因为：

- 全文重写；
- 单页重写；
- 教师手改；
- A/B/C版本；

都可能产生版本关系。

不能只不断覆盖一份正文，否则无法：

- 回退；
- 判断锁句来源；
- 审计 Final 来自哪个版本。

---

# 24. `draft_pages`

正文按页存储。

## 24.1 建议字段

| 字段 | 说明 |
|---|---|
| `draft_page_id` | 主键 |
| `draft_id` | 外键 |
| `page_number` | 1–8 / 1–12 |
| `page_text` | 当前页正文 |
| `created_at` | 时间 |
| `updated_at` | 时间 |

约束：

```text
UNIQUE(draft_id, page_number)
```

---

# 25. `draft_sentences`

建议 Demo 也保留句级数据。

## 25.1 原因

支持：

- 句子锁定；
- 单句长度统计；
- Pattern 匹配；
- 精确 Validation。

## 25.2 建议字段

| 字段 | 说明 |
|---|---|
| `sentence_id` | 主键 |
| `draft_page_id` | 外键 |
| `sentence_order` | 页内顺序 |
| `sentence_text` | 文本 |
| `locked` | bool |
| `locked_by_user_at` | 可空 |

原则：

> `page_text` 可以由 sentences 重建，或 sentences 由 page_text 重新解析；必须选定一种 authoritative runtime representation，避免双向同时人工编辑。

当前建议：

> **句子表为结构化运行表示，UI 页面文本由句子顺序合成。**

---

# 26. `planned_vocabulary`

保存正文生成前教师最终确认的计划词汇。

## 26.1 角色

Canonical role：

```text
CORE
EXTENSION_THEME
EXTENSION_CULTURAL
REVIEW
```

必要时可额外支持：

```text
NON_TEACHING_CONTEXT
UNCLASSIFIED
```

## 26.2 建议字段

| 字段 | 说明 |
|---|---|
| `planned_vocab_id` | 主键 |
| `project_id` | 外键 |
| `proposal_id` | 外键 |
| `raw_form` | 显示形式 |
| `normalized_form` | 标准形式 |
| `lemma` | V1 主要匹配单位 |
| `role` | canonical role |
| `teacher_confirmed` | bool |
| `ai_recommended` | bool |
| `source_lookup_status` | 来源 |
| `manual_review_required` | bool |
| `created_at` | 时间 |

## 26.3 为什么拆分主题拓展与跨学科拓展

体系总目标分别统计：

- 主题拓展词；
- 跨学科拓展词（含文学词汇）。

因此数据库层最好从一开始就区分：

```text
EXTENSION_THEME
EXTENSION_CULTURAL
```

UI 可以在某些页面统一显示为：

> 拓展词 Words to know

但底层角色不能全部丢成一个 `EXTENSION`。

---

# 27. `draft_vocab_observations`

保存某个 Draft 中实际检测到的词汇情况。

这是一张：

> **分析结果表**

不是教师正式词汇身份表。

## 27.1 建议字段

| 字段 | 说明 |
|---|---|
| `observation_id` | 主键 |
| `draft_id` | 外键 |
| `raw_form` | 正文形式 |
| `normalized_form` | 标准化 |
| `lemma` | lemma |
| `token_count` | 当前 Draft 内次数 |
| `planned_role` | 若命中 planned vocab |
| `detected_status` | planned / unclassified / ignored |
| `textbook_source_hit` | bool |
| `curriculum_source_hit` | bool（Power Up 2 语义 = 教材其他单元 TEXTBOOK_SCOPE 命中；字段名保留兼容） |
| `historical_conflict_hit` | bool |
| `manual_review_required` | bool |

每次正文变化后可重新生成。

---

# 28. `draft_pattern_observations`

保存核心句型检测结果。

## 28.1 建议字段

| 字段 | 说明 |
|---|---|
| `pattern_observation_id` | 主键 |
| `draft_id` | 外键 |
| `target_pattern` | 计划 Pattern |
| `normalized_pattern` | 用于匹配 |
| `matched_count` | 匹配次数 |
| `matched_sentence_ids_json` | 命中句 |
| `manual_review_required` | 是否需要人工复核 |

---

# 29. `vocabulary_confirmations`

记录教师“确认本版词表”的动作。

## 29.1 关键目的

不要只在 Draft 上写：

```text
vocab_confirmed = true
```

而应保留确认快照。

因为教师确认之后还可能继续改正文。

## 29.2 建议字段

| 字段 | 说明 |
|---|---|
| `confirmation_id` | 主键 |
| `draft_id` | 外键 |
| `confirmed_at` | 时间 |
| `confirmed_vocab_snapshot_json` | 当时待定稿词表 |
| `draft_content_hash` | 确认时正文 hash |
| `active` | 当前确认是否仍有效 |

## 29.3 失效规则

如果确认词表后正文发生任何影响词汇分析的编辑：

```text
draft_content_hash changes
```

则：

```text
active = false
draft.status = DRAFT
```

必须重新确认词表后才能 Final。

这是避免：

> “确认的是旧正文词表，但 Final 的却是新正文”

的关键一致性规则。

---

# 30. `validation_runs`

保存每次完整 / 局部 Validation 的运行记录。

## 30.1 建议字段

| 字段 | 说明 |
|---|---|
| `validation_run_id` | 主键 |
| `draft_id` | 外键 |
| `validation_type` | full / incremental / final_check |
| `content_hash` | 对应正文 |
| `started_at` | 时间 |
| `completed_at` | 时间 |
| `overall_status` | PASS / WARNING / BLOCKED |
| `rule_version` | 使用哪版 validation rules |

---

# 31. `validation_issues`

保存具体 Warning / Blocker。

## 31.1 建议字段

| 字段 | 说明 |
|---|---|
| `issue_id` | 主键 |
| `validation_run_id` | 外键 |
| `rule_key` | 规则 ID |
| `severity` | INFO / WARNING / BLOCKER |
| `scope_type` | book / page / sentence / word / pattern |
| `scope_ref_id` | 对应对象 |
| `message` | 给教师看的说明 |
| `resolution_status` | OPEN / ACKNOWLEDGED / RESOLVED / OVERRIDDEN |
| `resolved_by` | user / system |
| `resolution_note` | 人工备注 |

## 31.2 为什么需要记录 Warning 处理状态

因为 Final 前可能允许带 Warning 定稿。

系统必须知道：

> 教师是“没看到”，还是“明确看到并接受”。

否则无法审计。

---

# 32. `key_visuals`

保存参考视觉。

## 32.1 建议字段

| 字段 | 说明 |
|---|---|
| `key_visual_id` | 主键 |
| `project_id` | 外键 |
| `draft_id` | 可空 |
| `source_type` | GENERATED / UPLOADED |
| `file_ref` | 文件引用 |
| `prompt_or_note` | 可空 |
| `created_at` | 时间 |
| `active` | 当前是否使用 |

---


# 32A. `fact_reviews`

保存教师对事实性内容的人工核验记录。

Demo V1 不实现自动联网事实核验；系统只负责识别“可能需要核验”的内容。

## 建议字段

| 字段 | 说明 |
|---|---|
| `fact_review_id` | 主键 |
| `draft_id` | 外键 |
| `status` | NOT_REQUIRED / REQUIRED / VERIFIED_BY_USER |
| `verification_note` | 教师核验备注 |
| `verified_at` | 可空 |
| `content_hash` | 核验对应正文版本 |

Final 前如果正文需要事实核验，则必须满足：

```text
status = VERIFIED_BY_USER
verification_note is not empty
content_hash = current draft content hash
```

否则为 Final Blocker。

正文发生影响事实陈述的修改后，旧事实核验应失效并重新确认。


# 33. Final / Historical Data

---

# 34. `final_books`

这是正式历史绘本的核心表。

## 34.1 原则

`final_books` 不是把 Draft “移动过去”。

它保存：

> 某一次 Final 决策形成的不可变快照。

Draft 后续即使 Reopen 并修改，旧 Final 快照仍可留作审计，但：

```text
is_current = false
```

不再参与当前统计。

## 34.2 建议字段

| 字段 | 说明 |
|---|---|
| `book_id` | Final Book ID |
| `project_id` | 外键 |
| `draft_id` | Final 来源 Draft |
| `topic_id` | 外键 |
| `book_number` | 单元/Topic内正式序号 |
| `book_type_id` | 分类 |
| `title` | 标题快照 |
| `summary` | 一句话简介 |
| `page_count` | 页数 |
| `word_count` | 总词数 |
| `content_snapshot_json` | 分页正文 |
| `key_visual_ref` | 可空 |
| `finalized_at` | 时间 |
| `is_current` | 当前是否有效 |
| `superseded_by_book_id` | 重定稿后可关联新 Final |

---


# 34A. Unit Final 配额

Unit 完成状态由当前有效 `final_books` 动态计算，不人工维护计数器。

每个 Unit：

```text
总 Final：7（03语言项目收录标准：63 册 ÷ 9 Units）
三类分配（2026-08-19 人工确认）：
教材衔接 2 / 主题拓展 3 / 跨学科提升 2
```

可建立只读 View：

```text
topic_final_status
```

返回：

```text
topic_id
textbook_sync_final_count
theme_extension_final_count
cultural_awareness_final_count
total_final_count
completion_status
```

第 8 个及以后 Project / Draft 可以长期保留；只是无法在配额已满时继续成为新的当前有效 Final。


# 35. `final_book_vocabulary`

保存 Final 时正式确认的词汇角色。

## 35.1 Canonical Roles

建议：

```text
CORE
EXTENSION_THEME
EXTENSION_CULTURAL
REVIEW
NON_TEACHING_CONTEXT
```

注意：

> 一个 lemma 可以在不同 Final Books 中承担不同角色。

## 35.2 建议字段

| 字段 | 说明 |
|---|---|
| `final_book_vocab_id` | 主键 |
| `book_id` | 外键 |
| `raw_form` | Final 展示形式 |
| `lemma` | V1 统计单位 |
| `role` | 当前书中的正式角色 |
| `token_count` | 本书实际出现次数 |
| `source_status` | textbook / textbook_scope / unresolved |
| `manual_review_note` | 可空 |

约束建议：

```text
UNIQUE(book_id, lemma, role)
```

但如果未来允许同 lemma 的不同义项同时作为不同教学项目，需要升级数据模型。

---

# 36. `final_book_patterns`

保存 Final 核心句型。

## 36.1 建议字段

| 字段 | 说明 |
|---|---|
| `final_book_pattern_id` | 主键 |
| `book_id` | 外键 |
| `raw_pattern` | 教师确认的核心句 |
| `normalized_pattern` | Pattern |
| `repeat_count` | Final 内实际次数 |
| `source_relation` | textbook / adapted / other |

---

# 37. `recurrence_events`

复现统计必须使用“事件表”，不得只保存可变计数器。

## 37.1 为什么

错误做法：

```text
red.review_count = 3
```

然后：

- Final +1
- 撤销 -1
- 再 Final +1

很容易发生重复扣加和数据漂移。

正确做法：

```text
每一个有效 Final book × review lemma
= 1 条 recurrence event
```

累计次数随时：

```text
COUNT(valid recurrence_events)
```

得出。

---

## 37.2 建议字段

| 字段 | 说明 |
|---|---|
| `recurrence_event_id` | 主键 |
| `book_id` | 外键 |
| `level_id` | 外键 |
| `lemma` | 复现词 |
| `token_count_in_book` | 本书内部出现次数 |
| `event_value` | 当前固定为 1 |
| `is_active` | 是否参与当前统计 |
| `created_at` | 时间 |

唯一约束：

```text
UNIQUE(book_id, lemma)
```

因此：

> 同一本书里 red 出现 6 次，也只能形成 1 条 recurrence event。

---

# 38. `finalization_events`

记录 Final / Reopen / Re-final 的审计事件。

## 38.1 建议字段

| 字段 | 说明 |
|---|---|
| `event_id` | 主键 |
| `project_id` | 外键 |
| `book_id` | 可空 |
| `event_type` | FINALIZED / REOPENED / REFINALIZED |
| `occurred_at` | 时间 |
| `note` | 可空 |

这可以帮助排查：

> 为什么某个词昨天复现 3 次，今天变回 2 次？

---

# 39. `imported_historical_books`

历史 Excel 导入可以先进入 staging 表，而不是直接写 Final。

## 39.1 原因

旧数据可能缺：

- Topic；
- Book Type；
- review words；
- 完整正文；
- 状态字段。

所以建议：

```text
Excel
 ↓
imported_historical_books (staging)
 ↓
人工 / 程序校验
 ↓
确认
 ↓
final_books + final_book_vocabulary
```

## 39.2 建议字段

| 字段 | 说明 |
|---|---|
| `import_id` | 主键 |
| `source_file` | 来源 Excel |
| `raw_row_json` | 原始行 |
| `parsed_level` | 可空 |
| `parsed_topic` | 可空 |
| `parsed_title` | 可空 |
| `parsed_text` | 可空 |
| `parsed_core_words` | 可空 |
| `parsed_extension_words` | 可空 |
| `import_status` | PENDING / VERIFIED / REJECTED / IMPORTED |
| `manual_review_note` | 可空 |

---

# 40. Finalization 事务要求

Final 是一个事务性操作。

推荐：

```text
BEGIN TRANSACTION

1. 验证 Draft 最新 Validation 与正文 hash 一致
2. 验证 Vocabulary Confirmation 仍有效
3. 创建 final_books snapshot
4. 创建 final_book_vocabulary
5. 创建 final_book_patterns
6. 创建 recurrence_events
7. 写 finalization_event
8. 更新 project current Final
9. COMMIT
```

任一步失败：

```text
ROLLBACK
```

不得出现：

> Final Book 已生成，但 recurrence events 只写了一半。

---

# 41. Reopen / 撤销定稿事务要求

撤销 Final 时：

```text
BEGIN TRANSACTION

1. final_books.is_current = false
2. 对应 recurrence_events.is_active = false
3. 旧 Final vocabulary 不删除，只从“当前有效历史”中排除
4. project.status = REOPENED
5. 创建 finalization_event = REOPENED
6. COMMIT
```

不要物理删除历史 Final。

这样可以：

- 审计；
- 回滚；
- 避免统计错乱。

---

# 42. 历史冲突的计算方式

历史冲突不能依赖缓存字段。

Demo V1 只检查当前 Level 2。

查询逻辑：

```text
current candidate lemma
        ↓
final_book_vocabulary
        ↓
JOIN final_books
        ↓
WHERE final_books.is_current = true
JOIN topics ON final_books.topic_id = topics.topic_id
AND topics.level_id = current Level
AND historical role IN (CORE, EXTENSION_THEME, EXTENSION_CULTURAL)
```

历史仅作为 `REVIEW` 时不算冲突。跨 Level 暂不处理。

返回：

- Level；
- Semester；
- Unit；
- Topic；
- Book Number；
- Title；
- Historical Role。

---

# 43. 体系词汇进度的计算方式

首页统计建议实时或缓存计算自：

```text
final_book_vocabulary
JOIN final_books
WHERE final_books.is_current = true
```

Demo V1 分别按 lemma 去重计算：

```text
COUNT(DISTINCT lemma WHERE role = CORE)
COUNT(DISTINCT lemma WHERE role = EXTENSION_THEME)
COUNT(DISTINCT lemma WHERE role = EXTENSION_CULTURAL)
```

UI 必须标注：

> **按 lemma 统计，暂未区分 multiword / 一词多义。**

不得把：

- Proposal；
- Planned；
- Draft；
- 失效 Final；

计入“已沉淀”。

---

# 44. Review Pool / 待复现词池

建议不要建立一个人工维护的永久 `review_pool` 表作为唯一事实源。

更合理的是：

> 从**本地存储中当前有效 Final 的 Level 2 核心词** + 当前复现进度动态计算候选池。

可以建立缓存 / view，例如：

```text
review_pool_view
```

返回：

| 字段 | 说明 |
|---|---|
| `level_id` | 当前需要复现的 Level |
| `lemma` | 候选词 |
| `source_level` | 当前 Demo 固定为 Level 2 |
| `target_min` | 建议目标下限 |
| `target_max` | 建议目标上限 |
| `current_book_recurrence_count` | 当前次数 |
| `remaining_to_min` | 距最低目标差多少 |
| `eligible` | 是否可推荐 |

Level 2 候选池已确定：

```text
current active Final books
→ final_book_vocabulary.role = CORE
→ Level 2
→ 去重后形成候选池
```

冷启动：

```text
pool = 0   → 不要求复现词
pool = 1–4 → 有几个推荐几个
pool >= 5  → 建议 5–6 个
```

跨书累计 3–5 次仅作为建议目标，不作为 Final 硬约束。

---

# 45. 词汇身份优先级

同一本书中，一个 lemma 原则上不应同时拥有：

```text
CORE
EXTENSION
REVIEW
```

多个正式教学身份。

需要一个最终 canonical role。

建议优先由教师确认。

如果系统发现同一书同一 lemma 被分到多个角色：

> Validation Warning / Blocker

具体严重程度由 `04_validation_rules.md` 定义。

---

# 46. `NON_TEACHING_CONTEXT` 角色

原始标准提到：

> 未学过、但不影响理解、可从上下文或图片理解且不必掌握的词。

为了不把这些词与拓展词混淆，底层建议保留：

```text
NON_TEACHING_CONTEXT
```

这类词：

- 可以出现在正文；
- 不计入核心词；
- 不计入主题 / 文化拓展词目标；
- 可以单独统计；
- “每册不超过5个”在 Demo 中作为建议；超过 5 个显示 Warning，教师确认后仍可 Final。

---

# 47. Multiword Expressions

数据库必须允许：

```text
city centre
get dressed
have a shower
clean/brush your teeth
```

作为完整 lexical item 保存。

因此不能假设：

> 所有 vocabulary item 都是一个空格以内的 token。

建议字段：

```text
raw_form
normalized_form
lemma_or_canonical_form
is_multiword
```

V1 对 multiword 的 lemma 处理可以较保守：

> exact normalized phrase match + manual review warning

避免过度自动拆分。

---

# 48. 数据访问边界

LLM 不应拥有任意 SQL 权限。

应用层封装业务查询接口，例如：

```text
get_topic_reference(topic_id)
get_level_rules(level_id)
lookup_textbook_entry(form_or_lemma)
get_historical_vocab_usage(lemma)
get_review_candidates(level_id, topic_id)
get_current_project_context(project_id)
```

LLM 只能获得 Workflow 明确提供的结果。

---

# 49. RAG 与 Database 的优先级

如果存在权威结构化字段：

```text
Unit Title / Topic Theme
Textbook Words（全册范围）
Textbook Structures（Grammar）
Historical Usage
Recurrence Count
```

必须从 Database 获取。

不得用 RAG 检索结果覆盖。

RAG 只补充：

- 原则；
- 解释；
- 示例；
- 语义性指导。

---

# 50. LLM Output Write Boundary

LLM 输出只能先进入：

```text
candidate / draft data
```

不能直接写入：

```text
final_books
final_book_vocabulary
recurrence_events
```

Final 写入必须经过：

```text
Schema Validation
→ Program Validation
→ Teacher Confirmation
→ Transactional Finalization
```

---

# 51. 建议 SQLite View

为减少业务逻辑重复，可建立只读 View。

## `current_final_books`

```text
final_books
WHERE is_current = true
```

## `current_final_vocabulary`

当前有效 Final vocabulary。

## `current_recurrence_counts`

```text
GROUP BY level_id, lemma
COUNT(active recurrence events)
```

## `historical_vocab_usage`

返回每个 lemma 的历史有效使用位置与角色。

这些 View 不能替代底层事件记录。

---

# 52. 删除策略

## Static Reference

原始文档删除 / 停用时：

> 优先软停用 `active = false`

避免历史 Final 无法溯源。

## Runtime Draft

教师主动删除 Draft：

> 可软删除 / archived。

## Final

不得物理删除。

使用：

```text
is_current = false
```

并保留 finalization history。

---

# 53. 最低数据库约束

至少应有：

```text
Topic 唯一映射
Draft page number 唯一
Recurrence event: UNIQUE(book_id, lemma)
Final vocabulary: 防止同书同角色重复
Foreign keys enabled
Finalization 使用 transaction
```

SQLite 必须启用：

```text
PRAGMA foreign_keys = ON;
```

---

# 54. Demo V1 暂不要求的数据能力

当前不要求完整实现：

- 多教师 user_id；
- organization_id；
- 权限表；
- 云端同步冲突；
- 多义项 sense_id；
- 完整词族 family_id；
- 复杂 POS 语义转换；
- 向量 embedding 存 SQLite；
- 多语言教材版本；
- Level 3–6 全量运行。

但当前表设计应避免明显阻碍后续添加。

---

# 55. Data Dictionary 核心关系图

```text
LEVEL
  │
  ├─────────────── LEVEL_RULES
  │
  └── TOPIC
       ├────────── TEXTBOOK_WORDS
       ├────────── TEXTBOOK_STRUCTURES
       └────────── TEXTBOOK_EXAMPLES


CURRICULUM_ENTRIES
       │
       └────────── CURRICULUM_VARIANTS


TOPIC
  │
  └── PROJECT
       ├────────── PROJECT_OVERRIDES
       │
       ├── PROPOSAL
       │    ├───── PROPOSAL_VOCABULARY
       │    └───── PROPOSAL_PATTERNS
       │
       └── DRAFT_VERSION
            ├───── DRAFT_PAGES
            │        └──── DRAFT_SENTENCES
            ├───── DRAFT_VOCAB_OBSERVATIONS
            ├───── DRAFT_PATTERN_OBSERVATIONS
            ├───── VOCABULARY_CONFIRMATIONS
            ├───── VALIDATION_RUNS
            │        └──── VALIDATION_ISSUES
            └───── KEY_VISUALS


PROJECT
  │
  └── FINAL_BOOK
       ├────────── FINAL_BOOK_VOCABULARY
       ├────────── FINAL_BOOK_PATTERNS
       ├────────── RECURRENCE_EVENTS
       └────────── FINALIZATION_EVENTS
```

---

# 56. 当前 Product Overrides

本 Data Dictionary 按以下已确认决定设计：

```text
book_types:
  教材衔接
  主题拓展
  跨学科提升
```

```text
level_2_book_word_count:
  min = 120
  max = 200
```

```text
vocabulary_detection_v1:
  lemma normalization
  unresolved semantic cases → manual review warning
```

```text
proposal_to_fulltext:
  requires teacher selection
```

```text
dynamic_vocabulary:
  only current Final books participate
```

---

# 57. 与后续文档的接口

## `04_validation_rules.md`

需要基于本文件明确：

- 哪些 Warning 是 Blocker；
- Final 前哪些 Issue 必须 resolved；
- Level 2 各数值阈值；
- 非教学性情境词如何计数；
- 同一 lemma 多角色冲突怎么处理；
- 句型 Pattern 怎么统计；
- Fact Warning 怎么触发。

## `05_generation_rules.md`

需要明确：

- Proposal 输入使用哪些字段；
- Full Text 输入使用哪些字段；
- 如何把计划词 / 复现词提供给 LLM；
- 锁定句如何传递；
- Story / Language / Balanced 如何改变生成策略。

## `06_rag_mapping.md`

需要明确：

- RAG chunk metadata；
- task-specific retrieval scope；
- Database 与 RAG 的事实优先级；
- 哪些规则禁止进入 RAG 作为事实来源。

---

# 58. Data Dictionary 总原则

> **Static Reference Data 与 Runtime Data 分开。**

> **Proposal / Draft 的 AI 结果永远不等于 Final 事实。**

> **动态词汇身份属于 word × book × role，而不是词本身的永久属性。**

> **复现次数由有效 recurrence events 推导，不靠手工维护计数器。**

> **Final 是不可变快照；撤销 Final 通过失效处理，不物理删除历史。**

> **正文改变后，旧的词表确认和 Validation 必须失效。**

> **LLM 不直接访问任意 SQL，也不直接写正式历史数据。**

> **结构化事实优先 Database；RAG 不覆盖权威结构化字段。**

---

# Appendix A — Product Logic Review / 人工检查清单

以下仅保留尚未锁定、可能影响实现的项目：

1. **拓展词 Excel 展示**：数据库区分 `EXTENSION_THEME / EXTENSION_CULTURAL`；导出 Excel 是否继续合并为 `Words to know` 一列待确认。  
2. ~~三类绘本配额分配~~：已于 2026-08-19 人工确认为 教材衔接 2 / 主题拓展 3 / 跨学科提升 2。  
3. **非穷举教材词表**：Unit 6/7/8 教材词汇为“等”式列举，完整词表待人工补充；未命中词按 Warning 处理。  
4. **Book Number 分配**：建议 Final 时分配正式序号，需确认是否符合教研流程。  
5. **编辑版本策略**：教师连续手改建议 autosave；AI 重写生成新 Draft Version；“保存版本”形成 snapshot，需在前端实现前确认。  
6. **正文唯一事实源**：`draft_sentences` 与 `page_text` 必须选一个 authoritative representation，交由 Codex 根据前端技术方案确定。  
7. **Multiword / 一词多义正式出版统计口径**：Demo 按 lemma + 人工 override；正式体系后续再定。  
