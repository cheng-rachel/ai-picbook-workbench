# Power Up Picture Book Forge — RAG Mapping

> 文件路径建议：`01docs/05product/06_rag_mapping_v2.md`  
> 文档角色：定义 Power Up Picture Book Forge（Power Up 绘编）哪些原始资料进入 RAG、如何切分、携带什么 metadata、在什么任务中检索，以及 Database 与 RAG 的事实优先级。  
> 上位文档：`01_product_workflow_v2.md`  
> 数据来源依据：`02_data_mapping_v2.md`

---

# 1. 文档目的

本文件回答：

1. 哪些内容需要进入 RAG；
2. 哪些内容明确禁止进入 RAG 作为事实来源；
3. RAG chunk 如何切分；
4. chunk 需要哪些 metadata；
5. Proposal、正文、改写等任务分别检索什么；
6. 如何避免 RAG 与 Database 冲突；
7. 如何避免“搜到一段相似话就覆盖精确教材数据”；
8. Demo V1 的最小可用 RAG 架构。

核心原则：

> **RAG 负责找相关原则，不负责替代结构化事实数据库。**

---

# 2. RAG 的职责边界

RAG 适合：

- 编写理念；
- 分级解释；
- 主题拓展原则；
- 跨学科提升原则；
- 语用自然性；
- 词汇分类解释；
- 句型归类解释；
- 复杂边缘案例；
- 生成时需要的教研指导。

RAG 不适合：

- Topic 编号；
- 教材 Theme；
- Textbook Words；
- Textbook Structures；
- 教材词（全册范围）是否命中；
- 历史使用位置；
- 复现次数；
- Final 状态。

这些必须由 Database 提供。

---

# 3. 当前 RAG Source 范围

## 3.1 Source 01 — 设计理念与编写思路

主要进入 RAG。

候选主题：

```text
design_philosophy
textbook_alignment
graded_progression
scientific_recurrence
pragmatic_naturalness
factual_accuracy
```

---

# 4. Source 02 — 分级标准

只将解释性内容进入 RAG。

包括：

- 核心阅读目标；
- 主题梯度；
- 文化意识；
- 句式难度描述；
- 情节特征；
- 写作手法；
- 呈现形式。

不把已结构化数值作为 RAG 权威来源。

例如：

```text
Level 2 每页 2–3 句
```

即使原文 chunk 中存在，也必须以 Database / Product Override 为执行值。

---

# 5. Source 03 — 语言项目收录标准

部分进入 RAG。

重点：

```text
book_type_principles
theme_extension_guidance
cultural_awareness_guidance
vocabulary_collection_principles
recurrence_principles
core_pattern_definition
pragmatic_usage
```

数值型规则：

```text
8+4
3–5
5–6
```

可保留在 chunk 原文中用于解释，但不能作为运行时计算的唯一事实源。

---

# 6. Source 04 — Level 2 教材依据（教材词表）

Power Up 2 版本无独立课标词汇源；教材词表（全部 Unit 的 textbook words）：

> **不进入 RAG。**

原因：

- exact lookup 更重要；
- embedding 会产生误匹配；
- “语义相似”不能替代“是否属于教材词汇范围”。

所有教材词范围查询：

```text
Database only
```

---

# 7. Source 05 — Level 2 教材依据

## 7.1 不进入 RAG 的内容

以下权威字段：

```text
Theme
Essential Question
Words
Structure
Value
Topic mapping
```

全部：

```text
Database only
```

## 7.2 教材额外语句

Demo V1 正式采用：

> **不向量化；保存在 Database 中，按 Topic 精确读取后作为可选参考注入 Prompt。**

原因：

- 例句天然有明确 Topic；
- 不需要语义搜索猜测；
- 部分例句带 verified / pending 状态；
- 精确读取比向量检索更可靠。

Prompt 应明确：

> 这些例句仅作为教材语言与情境参考，不要求写入故事，也不得机械复制。

pending verification 的例句不得标记为已核验教材表达。

---

# 8. Product 文档是否进入 RAG

默认：

```text
docs/product/
```

不进入面向教师绘本生成的 RAG。

原因：

> Product docs 是系统实现规范，不是绘本创作知识。

它们用于：

- Codex；
- 开发；
- 测试；
- Workflow。

避免模型检索到：

> “FINAL must use transaction”

这种工程内容后混入故事生成。

---

# 9. RAG 最小数据结构

每个 chunk 至少包含：

```text
chunk_id
source_document
source_section
source_heading
text
rule_type
level_scope
book_type_scope
topic_scope
task_scope
verification_status
priority
```

---

# 10. `rule_type`

建议枚举：

```text
DESIGN_PHILOSOPHY
LEVEL_READING_GOAL
TOPIC_GRADIENT
CROSS_CURRICULAR
PLOT_GUIDANCE
WRITING_METHOD
PRAGMATIC_NATURALNESS
VOCABULARY_PRINCIPLE
RECURRENCE_PRINCIPLE
PATTERN_PRINCIPLE
FACTUAL_ACCURACY
BOOK_TYPE_GUIDANCE
```

---

# 11. `level_scope`

例如：

```text
ALL
LEVEL_2
LEVEL_3
...
```

生成 Level 2 时默认优先：

```text
LEVEL_2 + ALL
```

不得把 Level 5 的句法复杂度指导误检索到 Level 2。

---

# 12. `book_type_scope`

例如：

```text
ALL
TEXTBOOK_SYNC
THEME_EXTENSION
CROSS_CURRICULAR
```

如果当前 Proposal：

```text
CROSS_CURRICULAR
```

可以提升：

```text
CROSS_CURRICULAR
```

相关 chunk 权重。

---

# 13. `topic_scope`

大部分上位原则：

```text
ALL
```

如果未来某规则针对 Topic：

```text
TOPIC_7
```

则明确标注。

Demo V1 不应通过文本关键词自动猜 Topic scope。

---

# 14. `task_scope`

建议：

```text
PROPOSAL
FULL_TEXT
REWRITE
VOCAB_CLASSIFICATION
REVIEW_RECOMMENDATION
FACT_REVIEW
ALL
```

RAG 检索必须带当前 task scope。

---

# 15. Chunking 原则

## 15.1 按“规则单元”切，而不是固定字数硬切

优先：

```text
一个完整原则 / 一个完整表格解释 / 一个完整例子
= 一个 chunk
```

避免：

> 把一句规则前半段和后半段切开。

## 15.2 保留标题上下文

chunk 中应保留：

```text
document title
section
subsection
```

例如：

```text
03语言项目收录标准
→ 词汇收录补充说明
→ 派生词原则
```

---

# 16. Chunk 大小

Demo V1 建议以：

```text
约 150–500 中文字 / chunk
```

作为软参考。

如果一个规则很短：

> 不为了达到长度强行和无关规则拼接。

如果一个规则含完整例子：

> 可以适当更长。

---

# 17. 表格处理

对于解释性表格：

> 按“行 + 表头语义”转为自包含文本。

例如：

```text
Level 2 句型规则：
每册核心句型 1–2 个；
教材句型约占 85%；
核心句型重复 3–5 次；
可替换 1–2 个元素；
以简单陈述句、能力句、喜好句、简单祈使句等简单句为主。
```

但：

> 执行数值仍从 Database 获取。

---

# 18. 数据库与 RAG 冲突优先级

统一：

```text
Product Override
    ↓
Authoritative Database
    ↓
Current Teacher Input
    ↓
RAG Guidance
    ↓
LLM General Knowledge
```

注意：

Teacher Input 不能覆盖教材事实本身，但可作为：

> 当前生成 session override。

例如教师删除教材词：

> 不是修改教材事实，而是告诉生成器本次不使用。

---

# 19. RAG Retrieval 必须由 Workflow 指定

LLM 不得调用：

```text
search_all_rag()
```

自由检索。

Workflow 应调用受限接口，例如：

```text
retrieve_for_proposal(level, book_type)
retrieve_for_full_text(level, book_type)
retrieve_for_vocab_classification(level)
retrieve_for_rewrite(level, issue_types)
```

---

# 20. Proposal Retrieval

任务：

```text
GENERATE_PROPOSALS
```

建议检索：

```text
DESIGN_PHILOSOPHY
BOOK_TYPE_GUIDANCE
TOPIC_GRADIENT
PLOT_GUIDANCE
PRAGMATIC_NATURALNESS
LEVEL_READING_GOAL
```

如果：

```text
book_type = CROSS_CURRICULAR
```

额外提升：

```text
CROSS_CURRICULAR
```

---

# 21. Full Text Retrieval

任务：

```text
GENERATE_FULL_TEXT
```

建议检索：

```text
PRAGMATIC_NATURALNESS
LEVEL_READING_GOAL
PATTERN_PRINCIPLE
VOCABULARY_PRINCIPLE
RECURRENCE_PRINCIPLE
FACTUAL_ACCURACY
```

不得检索整个知识库后全部塞入 Prompt。

---

# 22. Rewrite Retrieval

根据实际问题检索。

例如 Validation Issue：

```text
core pattern repetition feels mechanical
```

则检索：

```text
PATTERN_PRINCIPLE
PRAGMATIC_NATURALNESS
```

若教师要求：

> “增加跨学科内容”

则检索：

```text
CROSS_CURRICULAR
BOOK_TYPE_GUIDANCE
```

---

# 23. Vocabulary Classification Retrieval

任务：

```text
SUGGEST_VOCAB_CLASSIFICATION
```

检索：

```text
VOCABULARY_PRINCIPLE
```

不检索完整故事写作原则。

Database 同时提供：

- 本单元教材命中；
- 教材全册（textbook scope）命中；
- 历史使用。

RAG 只提供：

> 如何理解词汇分类规则。

---

# 24. Review Recommendation Retrieval

复现候选词本身：

```text
Database
```

RAG 可以补充：

```text
RECURRENCE_PRINCIPLE
PRAGMATIC_NATURALNESS
```

帮助 LLM 判断：

> 哪些候选与当前故事更自然。

---

# 25. Fact Retrieval

Demo V1：

> RAG 中只有“事实准确性原则”，没有外部事实知识库。

因此涉及事实：

```text
RAG → 只能提醒原则
```

不能把 RAG 当作事实核验工具。

如果未来增加：

- 权威百科；
- 教参；
- 专业资料；

应建立独立：

```text
FACT_SOURCE RAG
```

并与教研原则 RAG 分开。

---


# 25A. Fact Sources / 事实资料

Demo V1 暂不建立自动 Fact Retrieval / Fact Verification 组件。

当前流程：

```text
系统识别可能需要核验的事实内容
→ 教师手动核验
→ 填写 verification note
→ 教师确认
→ 才可 Final
```

未来若加入国家标准、权威文化资料、自然科学资料等，例如：

```text
docs/fact_sources/
└── 某国家标准安全标志.pdf
```

应与 Teaching RAG 分离。

PDF 中的文字规则可进入独立：

```text
FACT_SOURCE RAG
```

PDF 中的真实图标 / 图像资产不应只依靠文本 embedding，应建立结构化记录并保留图像资产，例如：

```text
asset_id
asset_name
standard_name
page_number
meaning
image_asset_ref
source_document
verification_status
```

当前 Demo 只保留手动 Fact Check，不实现这一组件。


# 26. Retrieval 数量

Demo V1 建议：

```text
top_k = 3–6
```

再根据 metadata filter 缩小范围。

原则：

> 少而相关，优于多而混杂。

---

# 27. 去重

若多个 chunk 来自同一规则的重复表述：

> 检索后进行 semantic / source 去重。

避免 Prompt 中同一个规则重复五次，导致模型过度放大某一要求。

---

# 28. Priority

chunk 可带：

```text
priority = HIGH / NORMAL / LOW
```

例如：

```text
PRAGMATIC_NATURALNESS = HIGH
FACTUAL_ACCURACY = HIGH
```

故事示例：

```text
LOW / NORMAL
```

但 priority 不能覆盖 Database 事实优先级。

---

# 29. Verification Status

chunk 可带：

```text
VERIFIED
PENDING
PRODUCT_INTERPRETATION
```

例如：

- 原始教研明确规则 → VERIFIED
- Topic 4+ 未核验教材例句 → PENDING
- 产品对冲突后的执行解释 → PRODUCT_INTERPRETATION

生成时应尽量避免让 PENDING 内容成为核心依据。

---

# 30. RAG Prompt 注入格式

不要只把 chunk 原文裸拼接。

建议：

```text
[Guidance]
Source: 01设计理念与编写思路
Rule Type: PRAGMATIC_NATURALNESS
Priority: HIGH

Content:
...
```

这样模型更容易理解其角色：

> 这是指导原则，不是教材事实。

---

# 31. RAG 不允许覆盖数据库

若 RAG chunk 写有与执行值不一致的数值（假设示例）：

```text
Level 2 单篇 100–150 words（旧版本数值，Power Up 2 源中已不存在）
```

但当前 Database / Product Override：

```text
120–200
```

Prompt Assembly 必须提供：

```text
AUTHORITATIVE VALUE: 120–200
```

并且不得把冲突 RAG chunk作为执行值。

更理想做法：

> 对已被 Product Override 覆盖的数值，在 RAG processed data 中标记为 `non_authoritative_for_runtime_numeric_rules=true`。

---


# 31A. 当前已知数值冲突

目前明确存在（Power Up 2 源，02分级标准与03语言项目收录标准的单篇词数已一致为 120–200，旧篇幅冲突消失）：

## 核心词单篇复现

```text
03语言项目收录标准（表格）：3–5 次
03语言项目收录标准（正文）：有效复现 ≥3 次
Product Override：3–5 次为建议目标
```

## 跨册复现

原始资料存在：

```text
同级跨册复现 ≥3 册（表格）
跨册复现 3–5 次（建议）
```

当前产品解释：

> **3–5 仅作为建议目标，最低 ≥3 册；均不作为 Final 约束；不符合时显示 Warning。**

如果 RAG 保留这些原始数值 chunk：

```text
non_authoritative_for_runtime_numeric_rules = true
```

运行时执行值始终由 Database / Product Override 提供。


# 32. RAG 生成流程

```text
docs source
   ↓
extract allowed sections
   ↓
normalize headings
   ↓
rule-aware chunking
   ↓
attach metadata
   ↓
human-readable JSONL
   ↓
embedding
   ↓
index
```

建议输出：

```text
rag/processed/
├── design_principles.jsonl
├── level_guidance.jsonl
├── language_principles.jsonl
└── manifest.json
```

---

# 33. RAG Index

`rag/index/` 属于机器生成层。

不得人工维护。

源文档变化后：

```text
rebuild_rag
```

重新生成。

---

# 34. Source Hash

每个 chunk 应关联：

```text
source_hash
```

当原始文件变化时：

> 可检测旧 index 是否失效。

---

# 35. RAG Build Validation

至少检查：

1. chunk 是否有 source；
2. 是否有 rule_type；
3. 是否有 level_scope；
4. 是否有 task_scope；
5. 禁止源是否误入；
6. 是否存在空 chunk；
7. 是否存在大段重复；
8. 是否错误把工程文档放入生成 RAG；
9. 是否存在已知冲突数值但未标记非权威。

---

# 36. RAG Runtime Fallback

若检索不到相关 chunk：

> 不阻止基本生成。

系统仍可使用：

```text
Database facts
+ core generation rules
+ teacher input
```

不得：

> 因 RAG 空结果让 LLM 自己编造“项目规则”。

---

# 37. RAG Failure

如果向量索引不可用：

```text
RAG unavailable
```

应：

- 给开发日志 Warning；
- 继续使用 Database + Prompt core rules；
- UI 可选择是否提示“部分教研指导未加载”。

不要让整个系统直接崩溃。

---

# 38. Demo V1 最小实现建议

当前资料规模很小，Demo V1 正式优先采用：

> **本地 / 自托管 RAG index**

即与 Power Up 绘编 backend 一起部署，不接入独立云向量数据库。

可采用：

```text
small local vector index
+
metadata filtering
+
simple top-k retrieval
```

第一阶段也可以先用：

```text
rule-tagged JSONL + embedding
```

无需复杂知识图谱或云端 Vector DB。

---

# 39. 不要过度 RAG 化

以下任务完全不需要 RAG：

```text
Unit 8 是什么？
lost 是否在教材词汇范围？
red 历史出现在哪本书？
当前复现次数是多少？
这本书多少词？
```

这些必须：

```text
Database / Validation
```

---

# 40. Manual Check

1. **Fact Source RAG**：Demo 暂不实现；未来加入国标 PDF 等权威资料时单独设计。  
2. **冲突数值 chunk**：当前保留原文并标记 `non_authoritative_for_runtime_numeric_rules`；构建后需检查是否仍会误导模型。  
3. **本地 RAG 技术选型**：交由 Codex 根据依赖、部署与维护成本选择具体库。  
