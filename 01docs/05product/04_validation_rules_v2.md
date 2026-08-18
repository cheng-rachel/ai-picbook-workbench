# Power Up Picture Book Forge — Validation Rules

> 文件路径建议：`01docs/05product/04_validation_rules_v2.md`  
> 文档角色：定义 Power Up Picture Book Forge（Power Up 绘编）Demo 的程序校验逻辑、严重级别、Final 前检查条件与人工复核机制。  
> 上位文档：`01_product_workflow_v2.md`  
> 数据结构依据：`03_data_dictionary_v2.md`

---

# 1. 文档目的

本文件定义：

- 哪些规则由程序直接计算；
- 哪些结果属于 Info / Warning / Blocker；
- 哪些检查在 Proposal、Draft、Final Check 阶段触发；
- 哪些 Warning 可以人工接受；
- 哪些问题必须修复后才能 Final；
- Demo V1 中哪些复杂语言问题只做 lemma + 人工复核 Warning；
- Validation 如何与 Draft 内容版本、Vocabulary Confirmation、Final 状态保持一致。

Validation Engine 的职责是：

> **算和检查，不负责创作，不负责替教师做最终教研判断。**

---

# 2. 严重级别

统一使用以下四级：

## 2.1 `PASS`

规则满足。

示例：

```text
总词数：156 / 120–200 ✅
```

## 2.2 `INFO`

用于展示统计或提示，不要求处理。

示例：

```text
核心句型 A：本书出现 4 次
```

## 2.3 `WARNING`

存在偏离、来源不确定或需要人工判断的情况，但通常允许教师人工接受后继续。

示例：

```text
⚠️ lost 不在 Power Up 2 教材词汇范围内，请人工复核。
```

## 2.4 `BLOCKER`

若不解决，不允许 Final。

仅用于会导致数据状态不一致、关键内容缺失或无法安全确认的情况。

---

# 3. Validation 运行阶段

## 3.1 Proposal Validation

只做轻量检查：

- Proposal schema 是否完整；
- 预测核心词来源初查；
- Proposal 是否缺少完整故事线；
- 绘本分类是否为 canonical value。

不进行完整正文统计。

## 3.2 Draft Validation

正文生成及每次正文修改后自动运行：

- 页数；
- 总词数；
- 每页句数；
- 单句长度；
- 计划词实际出现；
- 未分类内容词；
- 复现词；
- 句型 Pattern；
- 教材范围来源（本单元 / 全册）；
- 历史冲突；
- 事实内容 Warning。

## 3.3 Final Check

点击 Final 前必须重新运行完整 Validation，并确保：

```text
validation.content_hash == current_draft.content_hash
```

否则旧 Validation 失效。

---

# 4. Level 2 当前有效参数

当前 Demo 使用：

```text
book_word_count_min = 120
book_word_count_max = 200
page_count_allowed = [8, 12]
sentences_per_page_target = 2–3
sentence_max_words_target = 10
core_pattern_target = 1–2
core_pattern_repeat_target = 3–5
review_words_per_book_target = 5–6
required_word_cross_book_recurrence_target = 3–5
```

说明：

- 120–200 是当前 Product Override；
- 句长、每页句数等属于 Level 2 目标；
- 不应为了满足数值破坏故事和语用自然性。

---

# 5. 页面数量检查

## Rule ID

```text
VAL-PAGE-001
```

## 规则

仅允许：

```text
8 pages
12 pages
```

## 严重级别

Draft：

```text
BLOCKER
```

因为页面数量是明确产品输入，不属于可模糊解释的语言质量问题。

---

# 6. 总词数检查

## Rule ID

```text
VAL-WORDCOUNT-001
```

## Level 2

```text
120 <= total_words <= 200
```

## 严重级别

Draft：

```text
WARNING
```

Final Check：

```text
WARNING + explicit acknowledgement required
```

原因：

> 词数范围是重要分级目标，但允许极少量边界情况由教研人员决定，不自动牺牲故事质量改写。

UI 示例：

```text
⚠️ 当前 207 词，超出 Level 2 目标上限 7 词。
[查看]
[我已确认，继续]
```

---

# 7. 每页句数检查

## Rule ID

```text
VAL-PAGE-SENT-001
```

## 规则

目标：

```text
2–3 sentences/page
```

## 严重级别

```text
WARNING
```

若某页为：

```text
0 sentence
```

则：

```text
BLOCKER
```

因为意味着正文结构不完整。

---

# 8. 单句长度检查

## Rule ID

```text
VAL-SENT-LEN-001
```

## 规则

Level 2：

```text
target <= 10 words
```

## 严重级别

```text
WARNING
```

系统必须逐句标出，而不是只显示全书平均值。

例如：

```text
P4 S2
The little dog quickly runs across the wet playground.
11 words ⚠️
```

注意：

> 句长超限不自动触发强制改写。

---

# 9. 核心句型数量检查

## Rule ID

```text
VAL-PATTERN-001
```

## 规则

Level 2：

```text
1–2 core patterns
```

## 严重级别

```text
WARNING
```

若教师没有确认任何核心句型：

```text
BLOCKER before Final
```

因为 Final 输出需要核心句字段。

---

# 10. 核心句型重复检查

## Rule ID

```text
VAL-PATTERN-002
```

## 规则

每个确认的核心 Pattern：

```text
target repetition = 3–5
```

统计按 Pattern，而不是逐字字符串一致。

例如：

```text
Where is my bag?
Where is my book?
Where is my coat?
```

统一计：

```text
Where is my ___? ×3
```

## 严重级别

```text
WARNING
```

原因：

> 句型重复必须服务真实情境，不应机械凑数。

---

# 11. Pattern 识别机制

优先级：

```text
1. 教师确认的 structured pattern
2. 教材 structure 的 normalized pattern
3. 规则匹配
4. AI 辅助判断
5. 人工复核
```

不得仅依赖 LLM 自由判断。

若系统无法稳定判断：

```text
manual_review_required = true
```

---

# 12. 计划核心词实际出现检查

## Rule ID

```text
VAL-CORE-001
```

每个 `planned_core_word` 至少检查：

```text
token_count >= 1
```

若：

```text
token_count = 0
```

则：

```text
WARNING
```

Final 前必须明确处理：

- 删除该计划核心词；
- 修改正文使其出现；
- 或教师重新确认词表。

---

# 13. 核心词单本频次

Level 2 当前采用（03语言项目收录标准）：

```text
建议每个核心词在单本中自然复现 3–5 次（有效复现 ≥3）
```

该次数不是硬性要求。

系统展示：

```text
token_count
```

若低于建议次数：

```text
WARNING
```

教师确认后仍可 Final。

原则：

> 不得为了消除 Warning 机械重复或破坏故事。

---

# 14. 计划拓展词检查

## Rule ID

```text
VAL-EXT-001
```

每个计划拓展词检查：

```text
是否实际出现
token_count
```

未出现：

```text
WARNING
```

但产品原则：

> 拓展词不要求机械用满，越少越好。

因此若正文不需要某拓展词，优先建议：

> 从计划词表移除

而不是强行插入正文。

---

# 15. 拓展词数量

Level 2 原始执行表中存在：

```text
8+4
```

当前产品解释：

```text
4 = 参考量 / 参考上限，不是必须填满
```

因此：

```text
extension_count <= 4
```

当前设为：

```text
WARNING when > 4
```

不设为 Blocker。

---

# 16. 未分类内容词检查

## Rule ID

```text
VAL-UNCLASSIFIED-001
```

正文中的内容词如果：

- 不属于计划核心词；
- 不属于计划拓展词；
- 不属于计划复现词；
- 且需要教学身份判断；

则进入：

```text
UNCLASSIFIED
```

Final 前：

```text
UNCLASSIFIED count > 0
→ BLOCKER
```

原因：

> 教师需要先确认这些词最终属于什么角色或是否不需要纳入教学词表。

---

# 17. 非教学性情境词

使用角色：

```text
NON_TEACHING_CONTEXT
```

用于：

> 没学过、不要求掌握、不影响理解、可从上下文或图片推断的词。

当前先统计：

```text
non_teaching_context_count
```

原始标准存在：

```text
每册不超过5个
```

Demo V1 正式采用：

```text
> 5 → WARNING
```

教师确认后仍可 Final，不升级为 Blocker。

---

# 18. 词汇来源检查

## Rule ID

```text
VAL-VOCAB-SOURCE-001
```

查询顺序：

```text
planned / pending-final word
        ↓
textbook_words（本单元）
        ↓
textbook_words（Power Up 2 全册 textbook scope）
        ↓
source status
```

可能结果：

```text
TEXTBOOK（本单元教材）
TEXTBOOK_SCOPE（教材其他单元）
UNRESOLVED
```

## 严重级别

未命中：

```text
WARNING
```

不得直接显示：

> “不在教材范围”即禁止

因为部分单元词表在源文档中为非穷举列举（Unit 6/7/8 的“等”），
当前加载的教材词表可能尚不完整。

---

# 19. Lemma 归一化

Demo V1：

```text
cars → car
children → child
went → go
```

用于：

- 来源查询；
- 历史冲突；
- 复现；
- 当前体系去重统计。

复杂情况只 Warning：

- 一词多义；
- 派生词；
- 词性转换；
- 固定搭配；
- 复杂合成词。

---

# 20. Multiword Expression 检查

例如：

```text
city centre
get dressed
have a shower
```

优先进行：

```text
normalized phrase match
```

不得在没有规则的情况下自动拆成多个“正式词汇项目”。

无法判定：

```text
manual_review_required = true
```

---

# 21. 同一书内词汇角色冲突

## Rule ID

```text
VAL-ROLE-001
```

同一 lemma 在同一本 Final 候选中原则上只能拥有一个主要教学角色：

```text
CORE
EXTENSION_THEME
EXTENSION_CULTURAL
REVIEW
NON_TEACHING_CONTEXT
```

若出现多角色：

```text
BLOCKER before Final
```

教师必须选定一个 canonical role。

---

# 22. 历史词汇冲突

## Rule ID

```text
VAL-HISTORY-001
```

查询：

```text
current_final_vocabulary
WHERE lemma = candidate
AND historical role IN:
  CORE
  EXTENSION_THEME
  EXTENSION_CULTURAL
```

若命中：

```text
WARNING
```

必须展示：

- Level；
- Unit；
- Topic；
- Book Number；
- Title；
- 历史角色。

允许：

```text
ACKNOWLEDGED / OVERRIDDEN
```

后继续 Final。

---

# 23. 历史冲突的 V1 匹配范围

Demo V1 只处理当前 Level 2。

```text
同 Level 内：
历史 CORE / EXTENSION_THEME / EXTENSION_CULTURAL
再次作为 CORE / EXTENSION
→ 红色 Historical Conflict Warning
```

历史仅作为：

```text
REVIEW
```

时不算冲突。

跨 Level 暂不处理。

V1 仍按 lemma 判断，不自动区分同词不同义，因此命中结果需提示人工复核。

---

# 24. 复现词实际出现检查

## Rule ID

```text
VAL-REVIEW-001
```

每个计划复现词：

```text
token_count >= 1
```

否则：

```text
WARNING
```

Final 前必须：

- 让词自然进入正文；
- 或从计划复现词中移除。

---

# 25. 复现事件计算

一个 Final Book 中：

```text
同一 review lemma
```

不论出现：

```text
1 次 / 4 次 / 8 次
```

跨书累计只产生：

```text
1 recurrence_event
```

约束：

```text
UNIQUE(book_id, lemma)
```

---

# 26. 复现进度展示

例如：

```text
red

本书出现：4 次
当前 Level：1/3
Final 后：2/3
```

这里：

- `4` = token frequency；
- `1/3` = book-level recurrence progress。

不得混为一个指标。

---

# 27. 复现目标区间

当前产品采用（03语言项目收录标准：同级跨册复现最低 ≥3 册，3–5 次为建议目标）：

```text
3–5 final books / level（最低 ≥3 册）
```

作为建议目标，而非约束条件。

系统展示：

```text
0–2 → 未达到建议目标，WARNING
3–5 → 建议区间
>5 → 超过建议区间，INFO / WARNING
```

均不阻止 Final。

---

# 28. 每册复现词数量与冷启动

Level 2 复现候选池来自：

> **本地存储中当前有效 Final 的 Level 2 核心词。**

```text
eligible pool = 0
→ 本书不要求计划复现词，不 Warning

eligible pool = 1–4
→ 有几个推荐几个，不 Warning

eligible pool >= 5
→ 建议计划 5–6 个复现词
```

当候选池 ≥ 5 时：

```text
<5 or >6 → WARNING
```

不设 Blocker。

一个词第一次作为 `CORE` Final 不计为复现；之后在其他 Final 绘本中以 `REVIEW` 身份出现，才产生 recurrence event。

---

# 29. 事实内容检测

## Rule ID

```text
VAL-FACT-001
```

若正文包含明显事实陈述，且属于：

- 自然；
- 健康；
- 文化；
- 历史；
- 生活常识；

生成：

```text
FACT_REVIEW_REQUIRED
```

Demo V1 可以由：

```text
LLM semantic classifier
```

辅助识别。

但：

> LLM 只能判“可能需要核验”，不能自行把事实标记为“已核验”。

---

# 30. 事实核验状态

使用：

```text
NOT_REQUIRED
REQUIRED
VERIFIED_BY_USER
```

若正文被标记为需要事实核验：

```text
status = REQUIRED
```

教师必须：

1. 手动完成核验；
2. 填写 `verification_note`；
3. 手动确认核验完成。

只有：

```text
status = VERIFIED_BY_USER
AND verification_note is not empty
```

才允许 Final。

否则：

```text
BLOCKER
```

Demo V1 不增加自动联网事实核验组件。

---

# 31. 教材补充语句核验状态

若使用：

```text
textbook_examples.verification_status = pending
```

作为生成参考，则 UI / Prompt context 应带：

```text
UNVERIFIED SOURCE
```

不得向教师展示为：

> 已核验教材语言。

---

# 32. Vocabulary Confirmation 有效性

教师点击：

> 确认本版词表

时保存：

```text
draft_content_hash
```

若正文后续变化：

```text
current_hash != confirmed_hash
```

则：

```text
confirmation.active = false
draft.status = DRAFT
```

Final：

```text
BLOCKER
```

直到重新确认词表。

---

# 33. Validation 有效性

Final Check 必须使用：

```text
current draft content hash
```

若最近一次完整 Validation 对应旧正文：

```text
BLOCKER
```

必须重新运行 Validation。

---

# 34. Final 状态检查

Final 前必须满足：

```text
current_draft exists
latest_full_validation matches current content
active vocabulary confirmation exists
no unresolved BLOCKER
```

否则：

```text
FINAL disabled
```

---

# 35. Warning Acknowledgement

部分 Warning 在 Final 前要求教师主动确认。

建议至少包括：

```text
word count outside target
historical conflict
unknown vocabulary source
fact verification warning
non-teaching context > target
```

记录：

```text
ACKNOWLEDGED
```

避免教师无意跳过。

---

# 36. Final Blocker

Demo V1 以下情况阻止 Final：

1. 页数不是 8 或 12；
2. 存在空白页；
3. 没有当前 Draft；
4. 没有有效 Vocabulary Confirmation；
5. Vocabulary Confirmation 对应旧正文；
6. Final Check 对应旧正文；
7. 存在未处理的 `UNCLASSIFIED` 教学内容词；
8. 同一 lemma 存在未解决的正式角色冲突；
9. 需要事实核验但未填写备注并确认；
10. 当前 Topic / 绘本类别的 Final 配额已满；
11. Final 写入事务失败。

其余教研类偏离原则上保持 Warning。

---

# 37. 修改后的自动重检范围

## 教师改正文

重新运行：

```text
word count
page sentence count
sentence length
vocabulary observations
pattern observations
history conflict
review detection
fact warning
```

## 教师只改词汇角色

无需重新生成正文，但必须重新运行：

```text
role conflict
source lookup
history conflict
review state
final vocabulary preview
```

## 教师只改 Key Visual

无需重新运行文本 Validation。

---


# 37A. Unit Final 配额校验

每个 Unit 必须最终形成（03语言项目收录标准：Level 2 共 63 册 ÷ 9 Units）：

```text
总 Final：恰好 7 本
三类数量分配（2026-08-19 人工确认）：
教材衔接 2 / 主题拓展 3 / 跨学科提升 2
```

校验执行总量配额与 per-type 子配额：

```text
current_final_count >= 7
再 Final 任何 Draft
→ BLOCKER（TOPIC_QUOTA_FULL）

同类型 current Final 数 >= 该类型上限（2 / 3 / 2）
再 Final 同类型 Draft
→ BLOCKER（BOOK_TYPE_QUOTA_FULL）
```

第 8、9……个 Project / Proposal / Draft 可继续长期保存和编辑，只是不允许成为新的当前有效 Final。

只有满足：

```text
current_final_count = 7
```

Unit 才标记：

```text
COMPLETED
```

否则：

```text
INCOMPLETE
```


# 38. Validation 输出格式

每次 Validation 返回结构化结果，例如：

```text
overall_status
summary
issues[]
metrics
content_hash
rule_version
```

Issue 至少包含：

```text
rule_key
severity
scope
message
resolution_options
```

---

# 39. Validation 不应做的事情

Validation Engine 不得：

1. 自动重写正文；
2. 自动删除超出范围词；
3. 自动把未知词改成简单词；
4. 自动决定词汇最终身份；
5. 自动解除历史冲突；
6. 自动把事实标为已核验；
7. 自动 Final。

它只负责：

> 发现 → 说明 → 提供可操作状态。

---

# 40. Manual Check

1. **Multiword / 一词多义正式出版口径**：Demo V1 允许教师人工 override，正式统计口径后续再定。  
2. **事实识别误报**：Fact Detector 可能把虚构情节误判为事实，需实测后调整触发范围。  
