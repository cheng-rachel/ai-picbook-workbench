# Power Up Picture Book Forge — Data Mapping

> 文件路径建议：`01docs/05product/02_data_mapping_v2.md`  
> 文档角色：定义 Power Up Picture Book Forge（Power Up 绘编）中，原始教研资料如何被自动提取、转换、校验，并映射到 Database、RAG、Prompt / Generation Rules、Validation Rules 与 Workflow。  
> 上位文档：`01_product_workflow_v2.md`

---

# 1. 文档目的

本文件回答以下问题：

1. `docs/` 中每一份原始教研资料由 Codex 提取什么；
2. 哪些内容进入结构化数据库；
3. 哪些内容进入 RAG；
4. 哪些内容不直接入库，而转化为 Prompt / Generation Rules；
5. 哪些内容转化为程序校验规则；
6. 原始资料之间发生冲突时如何记录；
7. 自动提取后如何校验；
8. 哪些数据属于静态源数据，哪些属于产品运行过程中动态产生的数据。

本文件不负责定义完整数据库字段类型、主键、外键和索引细节。

这些内容由：

> `03_data_dictionary.md`

进一步规定。

---

# 2. 总体数据原则

## 2.1 Source of Truth

人工维护的原始资料统一放在：

```text
docs/
```

包括：

```text
01docs/
├── 01绘本编写理念.docx
├── 02分级标准.docx
├── 03语言项目收录标准.docx
├── 04Level2教材依据.docx
└── 05product/
```

其中：

- `01docs/01–04` = 原始教研资料（Human Source of Truth）；
- `01docs/05product/` = 产品执行层规范。

原则：

> **原始 Word / Excel 是人工维护层的 Source of Truth。**

不得把 SQLite、JSON、RAG index 作为人工修改的首要来源。

---

## 2.2 派生数据

Codex 根据原始资料和产品规范自动生成：

```text
data/structured/
rag/processed/
rag/index/
```

例如：

```text
docs/
   ↓
自动解析 / 清洗 / 校验
   ↓
data/structured/
   ↓
SQLite
```

以及：

```text
docs/
   ↓
按 RAG Mapping 选取内容
   ↓
rag/processed/
   ↓
embedding / index
   ↓
rag/index/
```

---

## 2.3 禁止重复维护

不得出现以下工作方式：

```text
Word 改一次
SQLite 再手改一次
JSON 再手改一次
```

正确方式：

```text
修改原始 Word / Excel
        ↓
重新执行构建脚本
        ↓
structured data / SQLite / RAG 自动更新
```

---

# 3. 数据处理分类

每条原始信息必须被映射到以下一种或多种系统角色。

| 系统角色 | 用途 |
|---|---|
| Database | 精确事实、结构化参数、历史状态、可计算记录 |
| RAG | 需要语义理解或按任务检索的长文本原则与解释 |
| Generation Rules / Prompt | 每次生成时需要明确告诉模型的规则 |
| Validation Rules | 可由程序确定性检查或计算的规则 |
| Workflow | 决定在哪个阶段使用某条规则或数据 |
| Reference Only | 保留来源，但 Demo 当前不直接使用 |

一条原始规则可以同时进入多个系统角色。

例如：

> “核心语言要在不同册、不同级别、不同语境中科学复现。”

可以同时属于：

- RAG
- Generation Rules
- Workflow

但不应被错误地转化为一个简单数值字段。

---

# 4. 原始资料总映射

| 原始资料 | Database | RAG | Generation Rules | Validation Rules | Workflow |
|---|---:|---:|---:|---:|---:|
| 01绘本编写理念 | 少量 | 主要 | 主要 | 少量 | 是 |
| 02分级标准 | 主要 | 是 | 是 | 主要 | 少量 |
| 03语言项目收录标准 | 主要 | 是 | 主要 | 主要 | 主要 |
| 04Level2教材依据 | 主要 | 少量 | 动态注入 | 少量 | 少量 |

---

# 5. Source 01 — 绘本编写理念

## 5.1 原始文件

来源文件：

```text
01docs/01绘本编写理念.docx
```

该资料属于：

> **上位原则型数据**

不应整份机械结构化。

---

## 5.2 进入 RAG 的内容

以下部分保留完整语义：

### 设计理念

- 科学分级；
- 趣味故事；
- 同步教材知识；
- 能力培养；
- 自然习得语感。

### 教材衔接原则

- 以 Power Up 教材的单元学习内容为主要依据，与课堂学习进度相衔接；
- 综合参考教材的主题、核心词汇、核心句型、语用功能及相关语言知识；
- 不机械复述或改写教材原有故事，围绕单元主题和学习目标进行新的情境创作。

### 分级递进原则

包括：

- 儿童认知水平；
- 兴趣点；
- 生活经验；
- 思维能力；
- 文化理解；
- 情境理解；
- 信息提取；
- 阅读策略；
- 词汇；
- 句型复杂度；
- 语法项目；
- 语篇知识。

### 科学复现原则

- 不同册；
- 不同级别；
- 不同语境；
- 反复接触、理解和使用核心语言。

### 语用真实准确原则

- 符合真实生活情境；
- 符合故事情节逻辑；
- 符合英语表达习惯；
- 避免中文思维直译；
- 避免机械套用教材句型。

### 事实科学准确原则

- 自然；
- 健康；
- 文化；
- 生活常识；
- 不因降低语言难度牺牲事实准确性；
- 未经验证的 AI 事实内容不可直接视为可靠来源。

---

## 5.3 转化为 Generation Rules 的内容

提炼但不改变原意：

```text
GR-01 Story and pragmatic naturalness outrank mechanical language insertion.
GR-02 Textbook language is the basis, not a rigid story template.
GR-03 Repetition must occur naturally across meaningful contexts.
GR-04 Avoid Chinese-to-English literal translation.
GR-05 Simplification must not produce factual inaccuracy.
```

具体 wording 由：

> `05_generation_rules.md`

最终定义。

---

## 5.4 转化为 Workflow 的内容

涉及事实型内容时：

```text
正文生成
   ↓
识别是否涉及自然 / 健康 / 文化 / 历史 / 生活事实
   ↓
若是
   ↓
显示 Fact Verification Warning
```

Demo 第一版不要求自动联网事实核验。

---

## 5.5 不建议结构化的内容

以下内容不需要拆成大量数据库字段：

- “自然习得英语语感”
- “科学分级中搭建阶梯”
- “源于教材并高于教材”

这些属于上位理念，应作为 RAG / Generation Rules 使用。

---

# 6. Source 02 — 分级标准

## 6.1 原始文件

来源目录：

```text
01docs/02分级标准.docx
```

该资料属于：

> **Level 总纲型数据**

---

## 6.2 Database Mapping

按 Level 建立结构化记录。

建议提取以下维度：

```text
level
stage_positioning
core_reading_goal
topic_gradient
cultural_awareness
reading_word_count_description
vocabulary_requirement
sentence_requirement
sentence_complexity
text_types
plot_characteristics
writing_methods
presentation_format
```

其中能够明确数值化的内容应额外提取数值字段。

例如 Level 2：

```text
sentence_max_words = 10
core_pattern_min = 1
core_pattern_max = 2
sentences_per_page_min = 2
sentences_per_page_max = 3
```

---

## 6.3 RAG Mapping

以下内容保留为完整解释文本：

- 核心阅读目标；
- 主题梯度；
- 文化意识；
- 情节特征；
- 写作手法；
- 呈现形式；
- 对句式复杂度的文字描述。

原因：

> 这些内容虽然可以做标签，但真正生成故事时需要上下文语义，而不是单纯数值匹配。

---

## 6.4 Validation Mapping

明确数值型标准可用于自动检查：

- 单句词数；
- 每页句数；
- 核心句型数量；
- 全文词数范围。

但产品当前正式决策为：

> **Level 2 单篇总词数采用 120–200 words。**

当前版本 02分级标准 与 03语言项目收录标准 对篇幅一致（120–200），不存在篇幅冲突；
历史上（PEP 版本）曾存在 100–150 与 120–200 的冲突，该冲突在 Power Up 2 源中已消失。

---

## 6.5 冲突保留

原始资料若存在不同数值（当前实例：核心词复现次数与跨册复现的表格值 vs 正文描述）：

```text
Source A（03 表格）: 核心词单篇复现 3–5 次
Source B（03 正文）: 有效复现 ≥ 3 次
```

不得删除任一来源。

应记录：

```text
raw_value
source_document
source_section
product_effective_value
resolution_status
resolution_note
```

例如：

```text
raw_value = ≥3（正文） / 3–5（表格）
source_document = 03语言项目收录标准
product_effective_value = 3–5 次为建议目标
resolution_status = resolved_by_product_decision
resolution_note = 单篇核心词复现按 3–5 次为建议目标，不是 Final 硬约束
```

---

# 7. Source 03 — 语言项目收录标准

## 7.1 原始文件

来源目录：

```text
01docs/03语言项目收录标准.docx
```

该资料属于：

> **执行规则核心源**

同时映射到 Database、RAG、Generation Rules、Validation Rules 和 Workflow。

---

# 8. Source 03A — 绘本分类

## 8.1 Database Mapping

建立三类标准类型：

```text
textbook_sync
theme_extension
cross_curricular
```

产品显示名称统一为：

```text
教材衔接
主题拓展
跨学科提升
```

原始资料中的相关旧称（如 02分级标准维度「文化意识」、历史版本「文化对比」）：

不删除，但标准化映射为：

```text
跨学科提升（CROSS_CURRICULAR）
```

可保存：

```text
raw_label
canonical_label
```

---

## 8.2 建议结构化字段

每种类型可提取：

```text
book_type
core_positioning
relationship_to_textbook
usage_scenario
word_count_guidance
sentence_complexity_guidance
cognitive_goal
affective_goal
cross_disciplinary_guidance
```

---

## 8.3 RAG Mapping

以下完整描述进入 RAG：

- “换情境，练所学”
- “从主题出发，进一步思考”
- “借主题认识更大的世界”
- 教材衔接如何判断；
- 主题拓展如何判断；
- 跨学科提升如何自然切入；
- 跨学科角度优先贴合当前主题的说明；
- 原文中的故事主题示例（Unit 1 A day on the farm 三类案例）。

这些内容用于 Proposal 生成和分类判断。

---

# 9. Source 03B — Level 词汇参数

## 9.1 Database Mapping

从“每册词汇数据”提取各 Level 参数。

建议字段概念：

```text
level
cumulative_total_vocab
single_book_word_count_min
single_book_word_count_max
cumulative_core_vocab
new_core_words
extension_vocab
core_words_per_book
extension_words_per_book
increase_ratio_vs_previous
required_word_recurrence_min
required_word_recurrence_max
recurrence_mode
```

---

## 9.2 Level 2 产品有效值

当前正式产品决策：

```text
single_book_word_count_min = 120
single_book_word_count_max = 200
```

当前版本源表（03语言项目收录标准「分级词汇与篇幅标准」）与该决策一致（120–200），无篇幅冲突。

其他 Level 2 参数保留为（以 03 表格为准）：

```text
planned_books = 63（9 单元 × 7 册）
new_core_words_level2 = 504
cumulative_core_words = 882
core_words_per_book_reference = 8
extension_words_per_book_reference = 4
required_word_recurrence_target = 3–5
cross_book_recurrence_min = 3 册
```

注意：

> `8+4` 不等于必须严格生成 8 个核心词 + 4 个拓展词。

当前产品解释：

- 8 = 核心词参考数量；
- 4 = 拓展词参考上限 / 参考量；
- 拓展词越少越好，以故事真实表达需要为准。

---

# 10. Source 03C — 复现规则

## 10.1 Database Mapping

需要结构化保存：

```text
level
review_words_per_book_min
review_words_per_book_max
target_recurrence_min
target_recurrence_max
recurrence_unit
```

Level 2 当前产品解释：

```text
review_pool_source = current active Final Level 2 CORE words stored locally
review_words_per_book = 5–6 when eligible pool >= 5
target_recurrence = 3–5 (advisory only)
recurrence_unit = distinct_final_books_within_level
```

冷启动：

```text
pool = 0   → 不要求复现词
pool = 1–4 → 有几个推荐几个
pool >= 5  → 建议 5–6 个
```

---

## 10.2 动态统计定义

一个词在同一本书中出现多次：

```text
token_frequency = N
```

但跨书复现：

```text
book_level_recurrence_event = 1
```

只有 Final 绘本产生正式 recurrence event。

---

## 10.3 原始冲突记录

原文同时存在：

```text
同级别复现 3 次
```

和：

```text
必会词复现要求 3–5 次
```

当前产品使用：

```text
3–5 次（建议目标，不作为 Final 约束）
```

但必须保留：

```text
source_variants
```

不得删除“3次”的原始表述。

---

# 11. Source 03D — 词汇收录补充规则

原始规则包括：

- 一词多义列为新词；
- 短语动词及固定搭配原则上列为新词；
- 合成词原则上列为生词；
- 派生词原则上不列为生词；
- 词性转换后词义不变原则上不列为生词。

---

## 11.1 Demo V1 Mapping

Demo 第一版不自动实现完整语义规则。

只实现：

```text
lemma normalization
+
manual review warning
```

例如：

```text
cars → car
children → child
went → go
```

复杂情况：

```text
care → careful
water (noun) → water (verb)
a fixed expression
new sense of an existing lemma
```

统一标记：

> `manual_review_required = true`

---

## 11.2 RAG Mapping

完整词汇收录解释进入 RAG。

用于：

- AI 分类建议；
- 教师查看解释；
- 后续高级词汇判断。

---

## 11.3 Validation Mapping

程序只负责能确定的部分：

- lemma；
- exact source lookup；
- historical lookup；
- token frequency；
- category completeness；
- Warning 生成。

不得让 Demo V1 假装能够可靠完成词义级自动判定。

---

# 12. Source 03E — 语句收录标准

## 12.1 Database Mapping

按 Level 提取：

```text
level
core_pattern_min
core_pattern_max
textbook_pattern_ratio_target
pattern_repeat_min
pattern_repeat_max
replaceable_elements_min
replaceable_elements_max
sentence_difficulty_description
```

Level 2：

```text
core_pattern_min = 1
core_pattern_max = 2
textbook_pattern_ratio_target = 0.85
pattern_repeat_min = 3
pattern_repeat_max = 5
replaceable_elements_min = 1
replaceable_elements_max = 2
```

---

## 12.2 RAG Mapping

以下解释进入 RAG：

> 核心句型优先服务情境，其次按教材和教参中的教学目标判定，不按每个具体句子逐条拆分。

以及同一语言知识点 / 语用功能可归为同一 Pattern 的说明与例子。

---

## 12.3 Validation Mapping

程序应尽量基于：

```text
structured sentence pattern
```

进行统计。

例如：

```text
Where is my ___?
```

而不是完全自由地让 LLM 判断所有句型。

LLM 可作为辅助语义判断，但不作为唯一计数机制。

---

# 13. Source 04 —（已移除）课标词汇

Power Up 2 版本的 `01docs/` 不再包含独立的课标词汇源。

因此：

- 不再建立 `curriculum_vocabulary` / `curriculum_entries` / `curriculum_variants`；
- 词汇来源判定改为 **Power Up 2 教材全册词汇范围**（全部 Unit 的 `textbook_words`）：

```text
正文词形
   ↓
lemma normalize
   ↓
本单元 textbook_words
   ↓
其他单元 textbook_words（textbook scope）
   ↓
返回：
TEXTBOOK / TEXTBOOK_SCOPE / UNRESOLVED
```

- 词形变体（如 `leaf/leaves`、`clean/brush your teeth`）在提取时保留原文，
  查询时展开斜杠替代形式；
- 未命中时不自动判断为“不允许”，只返回 source warning / classification support。

---


# 14. Source 05 — Level 2 教材依据

## 14.1 原始文件

来源文件：

```text
01docs/04Level2教材依据.docx
```

该资料属于：

> **Level 2 Topic 主数据源**

主要进入 Database。

---

# 15. Source 05A — Topic 主表

原表字段：

```text
Title
Essential Question
Theme
Grammar
Cross-curricular
Literature
```

外加词汇表（教材要求词汇 1 / 2）。必须按 Unit 1–9 提取。

---

## 15.1 Database Mapping

建议映射：

```text
topic_number
level
semester
unit_number
unit_title
theme
essential_question
grammar_text
cross_curricular_text
literature_text
```

其中：

```text
Words
```

不要命名为：

```text
core_words
```

统一定义为：

```text
textbook_words
```

原因：

> 教材词汇是生成依据，不等于某一本绘本最终正式核心词。

同理：

```text
Grammar
```

映射为：

```text
textbook_structures
```

而不是直接叫：

```text
core_sentences
```

---

# 16. Source 05B — Textbook Words

建议进入独立关联结构。

概念：

```text
Topic
   ↕
Textbook Word
```

例如：

```text
Topic 8（Unit 8 Around town）
city centre
train station
car park
```

注意：

> 多词语言项目不得未经规则允许直接拆成单词。

例如：

```text
city centre
```

首先应作为教材原始语言项目完整保存。

后续词汇分析是否进一步拆分，由 Validation / vocabulary parser 决定。

---

# 17. Source 05C — Textbook Structures

每个 Topic 的教材结构单独保存。

例如：

```text
Past simple: more irregular verbs
have to / don't have to
How often …? and adverbs of frequency
```

需要保存：

- 原始结构文本；
- Topic；
- 来源；
- 顺序。

未来可额外人工定义：

```text
normalized_pattern
```

但第一轮自动提取不得擅自生成“权威 Pattern”。

---

# 18. Source 05D — 教材额外语句

文档中的“教材中额外涉及到的语句列表”应单独映射。

建议概念：

> `textbook_language_examples`

每条至少关联：

```text
topic
sentence
source_section
verification_status
```

---

## 18.1 Verification Status

当前 Power Up 2 源文档（04Level2教材依据.docx）不包含“教材额外语句列表”。

因此：

- `textbook_language_examples` 结构保留（兼容既有 schema），当前为空表；
- 后续人工补充额外例句时沿用 verification_status 字段记录核验状态；
- 系统不得静默把 pending 数据当作已核验数据。

Demo V1 中教材额外例句：

> **保存在 Database，按 Topic 精确读取；不进入向量 RAG。**

它们只作为生成故事时的参考语言，不要求一定写入正文。

---

# 19. Source 05E — Revision / Songs

当前 Power Up 2 源文档不包含 Revision / Songs 附录内容；本节保留为未来扩展位。
若后续人工补充，应保留：

建议与教材额外语句放在同一语言例句体系中，通过：

```text
source_section
```

区分。

例如：

```text
topic = nullable / related_topics
source_section = revision
```

或：

```text
source_section = songs
```

Demo V1 暂不要求复杂跨 Topic 自动映射。

可以：

- 保留 source section；
- 保留原始顺序；
- 在需要时由 AI / 人工关联。

---

# 20. Product 文档的 Mapping

`01docs/05product/` 中的文档不是教材事实数据。

它们属于：

> **产品执行规范**

不进入普通教材内容数据库。

---

## 20.1 `01_product_workflow_v2.md`

用途：

- 工程实现；
- Workflow Orchestrator；
- UI；
- 状态机；
- Final / Reopen 逻辑。

不做 RAG 主内容源，除非未来需要开发者问答。

---

## 20.2 `02_data_mapping_v2.md`

即本文件。

用于：

- 数据构建脚本；
- ETL；
- source → target 映射；
- 自动构建流程。

---

## 20.3 后续产品规范

```text
03_data_dictionary.md
04_validation_rules.md
05_generation_rules.md
06_rag_mapping.md
```

分别控制：

- 数据结构；
- 程序校验；
- LLM生成；
- RAG构建。

---

# 21. 静态数据与动态数据必须分开

## 21.1 静态源数据

来自原始教研材料，例如：

- Level 规则；
- Topic / Unit；
- 教材词汇（Power Up 2 全册）；
- 教材结构；
- 编写原则。

特点：

> 由 `docs/` 构建。

---

## 21.2 动态产品数据

来自教师实际使用，例如：

- Proposal；
- Selected Proposal；
- Draft；
- planned core words；
- planned extension words；
- planned review words；
- pending-final vocabulary；
- Final；
- historical word roles；
- recurrence events；
- Key Visual；
- version snapshots。

特点：

> 由 App 运行产生。

不得通过重新解析原始 Word 覆盖。

---

# 22. Historical Books Mapping

目录：

```text
data/historical_books/
```

用于导入系统建立之前已经正式完成的绘本。

典型来源：

```text
Excel
```

历史数据只有在明确标记为：

> Final / 已定稿

后，才能参与：

- 历史核心词冲突；
- 历史拓展词冲突；
- 复现统计；
- 体系词汇进度。

---

## 22.1 历史书导入原则

历史 Excel 至少需要映射：

```text
level
semester
unit
topic
book_number
book_type
title
summary
text
core_patterns
core_words
extension_words
review_words
status
```

缺失字段允许：

> null / pending manual review

不得让 LLM 自动补全并当作历史事实。

---

# 23. Dynamic Vocabulary Mapping

动态词汇不能建模成：

```text
word → permanent category
```

必须建模为：

```text
word × book × role × status
```

例如：

```text
find
Book 023
role = core_word
status = final
```

同一个词在另一绘本可能是：

```text
find
Book 041
role = review_word
status = final
```

因此：

> 词的角色属于“词在某一本书中的教学身份”，而不是 lemma 的永久属性。

---

# 24. Vocabulary Lifecycle Mapping

## Proposal

```text
predicted_core_words
predicted_extension_words
```

不进入正式动态词库。

---

## Pre-generation

```text
planned_core_words
planned_extension_words
planned_review_words
```

不进入正式动态词库。

---

## Draft

正文分析生成：

```text
actual_token_frequency
unclassified_content_words
source_lookup_result
historical_conflict_result
```

---

## Vocabulary Confirmed

形成：

```text
pending_final_core_words
pending_final_extension_words
pending_final_review_words
```

仍不进入正式统计。

---

## Final

写入：

```text
final vocabulary roles
recurrence events
historical usage
```

---

# 25. Proposal 数据 Mapping

Proposal 属于动态产品数据。

至少需要保存：

```text
proposal_id
project_id
topic_id
proposal_title
entry_point_cn
storyline
predicted_core_words
predicted_core_patterns
predicted_extension_words
book_type
plot_structure
potential_issues
creative_highlight
created_at
selected_status
```

Proposal 不进入动态词汇库。

---

# 26. Full Text 数据 Mapping

每个正文版本至少需要保存：

```text
draft_id
proposal_id
version_number
generation_orientation
page_count
pages
word_count
planned_core_words
planned_extension_words
planned_review_words
validation_snapshot
created_at
updated_at
status
```

正文以：

> page

为基本内容单位。

不要只保存一整块长文本，否则：

- 单页重写；
- 页面锁定；
- 页级 Validation；

会变得困难。

---

# 27. Sentence Lock Mapping

教师锁定句子时，应保存：

```text
draft_id
page_number
sentence_id
locked = true
```

后续全文或单页 AI 重写必须把锁定内容作为不可修改约束。

---

# 28. Key Visual Mapping

Key Visual 属于可选动态数据。

保存：

```text
book / draft reference
image_path_or_reference
generation_or_upload
created_at
```

不需要进入 RAG。

---

# 29. Source Provenance

所有从原始资料提取的结构化数据都应尽量可溯源。

建议至少保留：

```text
source_document
source_section
source_version_or_hash
extraction_timestamp
```

重要规则 / 参数可额外保存：

```text
raw_text
```

目的：

> 当教师或开发者质疑某条规则时，可以追溯“它来自哪一份原始资料”。

---

# 30. Canonicalization Rules

自动构建时需要统一以下内容。

## 30.1 Book Type

所有同义原始标签：

```text
文化对比
文化对比型
文化意识（作为绘本分类时）
跨学科提升
```

产品 canonical value：

```text
跨学科提升（CROSS_CURRICULAR）
```

---

## 30.2 Topic

必须标准化为：

```text
Topic 1
...
Topic 9
```

同时保存：

```text
semester
unit_number
```

不得只依赖 Topic 文本推断 Unit 归属。

---

## 30.3 Vocabulary

至少标准化：

- lowercase lookup form；
- lemma；
- raw form；
- multiword status。

展示时仍可以保留教材原始大小写与写法。

---

## 30.4 Sentence / Structure

必须保留原始文本。

不得在 ETL 阶段：

- 自动改写语法；
- 自动“纠错”；
- 自动润色教材原句。

如果发现疑似问题：

> 写入 extraction / validation warning

而不是静默修改 Source。

---

# 31. 构建后的建议中间文件

`data/structured/` 可由 Codex 自动生成例如：

```text
data/structured/
├── level_rules.json
├── book_types.json
├── level2_topics.json
├── textbook_words.json
├── textbook_structures.json
├── textbook_language_examples.json
├── source_conflicts.json
└── picbook_forge.sqlite
```

这些只是推荐命名。

最终是否保留所有 JSON，由 Codex 根据实现决定。

原则：

> 应保留至少一种人类可读的 structured intermediate，用于核验自动提取结果。

---

# 32. RAG 输入来源

当前 RAG 不应该默认把所有 Word 全量切块。

候选来源主要为：

```text
01绘本编写理念
02分级标准中的解释性内容
03语言项目收录标准中的解释性原则
```

以下通常不进入 RAG：

```text
04Level2教材依据 Topic 主表中的精确字段与教材词表
```

因为这些内容数据库查询更准确。

具体 chunking、metadata 和 index 规则由：

> `06_rag_mapping_v2.md`

定义。

---

# 33. Validation 数据来源优先级

程序检查时，应优先使用结构化数据。

例如：

## 核心词来源检查

```text
planned core word
   ↓
textbook_words（本单元）
   ↓
textbook_words（全册 textbook scope）
   ↓
result
```

不是：

```text
planned core word
   ↓
问 LLM “是不是教材词？”
```

---

## Topic 教材信息

```text
selected topic
   ↓
topics table
```

不是：

```text
RAG 搜索哪个 Topic 好像相关
```

---

## 复现统计

```text
Final vocabulary / recurrence database
```

不是：

```text
LLM 回忆历史绘本
```

---

# 34. Conflict Resolution

原始资料之间发生冲突时：

## 34.1 不静默覆盖

必须同时保留：

```text
Source A value
Source B value
```

## 34.2 产品有效值单独记录

例如 Level 2 单篇词数：

```text
Source 03（表格）:
核心词单篇复现 3–5 次

Source 03（正文）:
有效复现 ≥ 3 次

Current Product Decision:
3–5 次为建议目标（不是 Final 硬约束）
```

## 34.3 产品决策优先于自动推断

当 `01docs/05product/` 已明确决定时：

> 构建脚本使用 product effective value。

不得让 Codex 根据“哪份文档看起来更具体”自行重新决定。

---

# 35. 自动提取校验流程

建议构建脚本按以下步骤运行：

```text
1. Scan docs/
      ↓
2. Parse source documents
      ↓
3. Extract structured candidates
      ↓
4. Normalize canonical values
      ↓
5. Validate required fields
      ↓
6. Compare expected counts / ranges
      ↓
7. Generate extraction warnings
      ↓
8. Produce human-readable structured files
      ↓
9. Build / update SQLite
      ↓
10. Build RAG processed data where applicable
```

---

# 36. 必做的 Source Validation

## 36.1 Topic 数量

Level 2 应得到：

```text
10 Topics
```

若不是 10：

> build warning / failure

---

## 36.2 Topic 必填字段

每个 Topic 至少应有：

```text
Theme
Essential Question
Words
Structure
Value
```

缺失时：

> extraction warning

---

## 36.3 Textbook Words（全册范围）

自动检查：

- 空条目；
- 重复条目；
- 大小写重复；
- 斜杠变体 parsing（如 leaf/leaves）；
- 多词表达；
- 非穷举列举（“等”）的 warning 标记；
- 明显异常符号。

源文档中为非穷举列举（Unit 6/7/8 的“等”）时：

> 不自动删除或补词；
> 输出 Warning。

---

## 36.4 Level Rules

检查：

- 数值范围是否 min <= max；
- 是否存在相互冲突来源；
- 是否已有 product effective value。

---

## 36.5 Textbook Examples

必须保存：

```text
verification_status
```

特别是未完成教研核验的 Topic 语言例句。

---

# 37. Build Failure 与 Warning

建议区分：

## Build Failure

仅用于无法安全继续构建的错误，例如：

- Topic 编号重复；
- 主表缺失 Topic；
- 必需 source 文件无法读取；
- 数据结构无法解析。

## Warning

例如：

- 某词未解析出 variant；
- 原始数值冲突；
- Topic 4+ 补充语句未核验；
- 词汇表标题数量与实际提取数量不同；
- 疑似教材文本格式错误。

原则：

> Warning 不应被自动“修好”。

---

# 38. 不允许 Codex 在 ETL 阶段做的事情

Codex 不得：

1. 擅自改写教材句子；
2. 用常识替换原始教研规则；
3. 自动选择冲突规则中的“更合理版本”；
4. 用 LLM 补齐缺失教材字段并当作事实；
5. 把 Topic Words 自动全部认定为某本绘本 Core Words；
6. 把未经确认的 AI 分类写入正式动态词库；
7. 把 Draft 当成历史 Final；
8. 把所有原始 Word 全部无差别进入 RAG；
9. 因为结构化方便而删除 raw entry；
10. 在没有记录来源的情况下修改 canonical value。

---

# 39. 建议构建脚本职责

未来 `scripts/` 可以包括：

```text
scripts/
├── extract_level_rules.py
├── extract_language_project_rules.py
├── extract_level2_topics.py
├── validate_sources.py
├── build_database.py
├── build_rag.py
└── rebuild_all.py
```

具体文件名可由 Codex调整。

核心要求：

> 构建过程必须可重复执行。

---

# 40. Rebuild 原则

当人工修改：

```text
docs/01–05
```

后，可以重新构建：

```text
structured static data
SQLite static reference tables
RAG processed/index
```

但不得覆盖：

```text
teacher projects
drafts
Final books
dynamic vocabulary history
recurrence records
manual review decisions
```

因此实现时应明确区分：

> Static Reference Data

与：

> Runtime / User Data

---

# 41. 推荐的数据流

```text
                HUMAN-MAINTAINED
                       │
                       ▼
                    docs/
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
 Structured Extraction        RAG Extraction
          │                         │
          ▼                         ▼
 data/structured/             rag/processed/
          │                         │
          ▼                         ▼
     Static SQLite              rag/index/
          │                         │
          └────────────┬────────────┘
                       ▼
                 Application
                       │
                       ▼
               Runtime Database
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       Drafts        Finals     Recurrence
                       │
                       ▼
                    Exports
```

---

# 42. 当前已锁定的 Product Overrides

构建脚本必须读取或硬编码为显式配置，而不能重新推断：

```text
book_type_canonical_names:
  - 教材衔接
  - 主题拓展
  - 跨学科提升
```

```text
level_2_single_book_word_count:
  min: 120
  max: 200
```

```text
vocabulary_detection_v1:
  method: lemma_normalization
  unresolved_cases: manual_review_warning
```

```text
proposal_to_fulltext:
  human_selection_required: true
```

```text
formal_vocabulary_write:
  only_when_book_status_is_final: true
```

```text
project_model:
  one_project_one_final_book: true
  multi_selected_proposals_create_independent_projects: true
```

```text
topic_final_quota:
  total_final_books: 7   # 03语言项目收录标准：63 册 ÷ 9 Units
  per_book_type:         # 2026-08-19 人工确认
    TEXTBOOK_SYNC: 2     # 教材衔接
    THEME_EXTENSION: 3   # 主题拓展
    CROSS_CURRICULAR: 2  # 跨学科提升
  extra_drafts_allowed: true
```

```text
fact_review:
  automated_fact_retrieval_in_demo: false
  manual_check_required_when_flagged: true
  verification_note_required: true
  unresolved_fact_review_blocks_final: true
```

```text
homepage_vocab_progress:
  counting_method: distinct_lemma
  ui_note: 按 lemma 统计，暂未区分 multiword / 一词多义
```

---

# 43. 本文件与后续规范的边界

本文件只回答：

> **“原始资料里的什么内容，应该被送到系统的哪里？”**

下一份：

> `03_data_dictionary.md`

回答：

> **“数据库里具体有哪些实体、字段、类型、关系和状态？”**

之后：

> `04_validation_rules.md`

回答：

> **“程序到底怎么算、什么算 Pass、什么显示 Warning？”**

之后：

> `05_generation_rules.md`

回答：

> **“Proposal、正文、重写、复现词推荐时，LLM具体遵守什么？”**

最后：

> `06_rag_mapping.md`

回答：

> **“哪些原始段落进入 RAG，怎么切块、带什么 metadata、什么时候检索？”**

---

# 44. Data Mapping 核心原则

整个数据转换过程遵循：

> **原始资料保持原样。**

> **结构化事实进入 Database。**

> **解释性原则进入 RAG。**

> **生成必须遵守的原则进入 Generation Rules。**

> **可以确定性计算的要求进入 Validation Rules。**

> **教师和产品已经明确解决的冲突，以 Product Override 为当前执行值。**

> **Codex 负责自动提取和构建，不负责重新发明教研规则。**


---

# 45. Manual Check

1. ~~三类绘本配额分配~~：已于 2026-08-19 人工确认为 教材衔接 2 / 主题拓展 3 / 跨学科提升 2。  
2. **非穷举教材词表**：Unit 6/7/8 词表为“等”式列举，未命中只能保持 Warning。  
3. **拓展词 Excel 展示**：底层分角色保存；导出是否合并一列待确认。  
