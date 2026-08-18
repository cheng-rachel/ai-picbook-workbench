# Power Up Picture Book Forge — Generation Rules

> 文件路径建议：`01docs/05product/05_generation_rules_v2.md`  
> 文档角色：定义 Power Up Picture Book Forge（Power Up 绘编）中 LLM 在 Proposal、复现词推荐、正文生成、重写和语言分类建议等任务中的输入边界、生成原则与输出结构。  
> 上位文档：`01_product_workflow_v2.md`  
> 数据与状态依据：`03_data_dictionary_v2.md`  
> 校验依据：`04_validation_rules_v2.md`

---

# 1. 文档目的

本文件规定：

- LLM 在不同任务中允许获得什么上下文；
- 哪些事实必须由 Database 提供；
- 哪些原则由 RAG 提供；
- Proposal 如何保证真正多样；
- Full Text 如何保持 Proposal 骨架；
- 计划词、复现词和核心句型如何自然进入故事；
- AI 可以建议什么、不能决定什么；
- 如何避免“为了指标而写坏故事”。

核心原则：

> **LLM 是创作与语义判断组件，不是事实数据库，也不是最终教研决策者。**

---

# 2. 资源路由原则

LLM 不自行决定：

- 查哪个数据库；
- 是否使用 RAG；
- 哪个来源优先；
- 是否写入 Final。

资源路由统一由：

> **Workflow / Orchestrator**

控制。

若存在权威结构化字段：

> 必须从 Database 获取，不得让 RAG 或 LLM 猜测。

---

# 3. LLM 输入层级

每次生成任务的 Prompt Context 建议按以下层级组装：

```text
1. SYSTEM / PRODUCT RULES
2. TASK TYPE
3. AUTHORITATIVE DATABASE FACTS
4. TASK-SPECIFIC RAG GUIDANCE
5. CURRENT PROJECT STATE
6. TEACHER INPUT
7. REQUIRED OUTPUT SCHEMA
```

优先级从上到下递减。

---

# 4. 通用最高优先级生成原则

所有生成任务必须遵守：

## GR-01 教材有据

教材 Theme、Essential Question、Textbook Words、Textbook Structures、Value 等只能使用系统提供的数据。

不得凭模型记忆补教材内容。

## GR-02 故事逻辑优先

不得为了：

- 塞核心词；
- 塞复现词；
- 凑句型次数；
- 凑拓展词；

破坏故事因果、角色动机和场景真实性。

## GR-03 语用自然

英语必须符合：

- 实际交际情境；
- 儿童语境；
- 英语表达习惯。

避免：

- 中文思维直译；
- 生硬模板句；
- 为使用教材句型而制造不合理对话。

## GR-04 分级适配

Level 2：

- 语言简洁；
- 句型重复度较高；
- 情节清晰、容易预测；
- 主要依赖简单句；
- 插图应能帮助理解。

## GR-05 拓展克制

拓展词：

> 只在故事真实表达需要时使用。

不得为了达到“丰富度”主动增加难词或新概念。

## GR-06 科学复现

复现词应进入新的自然语境。

跨书累计 3–5 次属于建议目标，不是 Final 约束；未达到由 Validation 提示 Warning。

不得生成：

> 与故事无关、只为了出现一次的句子。

## GR-07 事实准确

涉及事实内容：

- 不得编造；
- 不因语言简化而改变事实；
- 若缺乏可靠依据，输出中标记需要核验，而不是自信断言。

## GR-08 教师优先

教师明确输入高于 AI 自主偏好，但不能覆盖：

- 数据真实性；
- 系统安全；
- 已锁定的 Final 状态规则。

---

# 5. Proposal Generation

任务：

```text
GENERATE_PROPOSALS
```

默认输出：

```text
6–10 proposals
default = 8
```

---

# 6. Proposal 输入

必须包括：

## Database

- Level；
- Semester；
- Unit；
- Topic；
- Theme；
- Essential Question；
- Textbook Words；
- Textbook Structures；
- Value；
- 相关教材语言例句；
- Book Type canonical values。

## RAG

按任务检索：

- Level 2 编写原则；
- 教材衔接 / 主题拓展 / 跨学科提升原则；
- 故事与语用原则。

## Teacher Input

- session overrides；
- 希望使用 / 避免的内容；
- 额外创作要求。

---

# 7. Proposal Diversity Planner

正式生成 Proposal 前执行隐藏规划。

每个 Proposal 应尽量在至少 2–3 个维度与其他 Proposal 产生实质差异：

```text
setting
central_problem
plot_driver
resolution_mechanism
ending
narrative_form
cognitive_angle
```

禁止：

> 只换动物、人物名字、地点或道具。

可参考：

- 校园；
- 家庭；
- 自然；
- 游戏 / 挑战；
- 社会生活；
- 科学发现；
- 奇幻想象；
- 文化情境。

这些不是固定配额。

---

# 8. Proposal Storyline

每个 Proposal 必须包含：

```text
setup
problem / goal
development
main turn / repetition logic
resolution / ending
```

不能只输出：

> “一个关于坚持的故事。”

需要让教师能判断故事是否值得继续。

---

# 9. Proposal 输出 Schema

每个 Proposal：

```text
title
entry_point_cn
storyline
predicted_core_words
predicted_core_patterns
predicted_extension_words
book_type
plot_structure
potential_issues
creative_highlight
```

输出必须可被程序解析。

---

# 10. Proposal 预测词原则

## 预测核心词

优先顺序：

```text
1. 当前 Unit Textbook Words
2. 系统提供的教材全册（textbook scope）候选
3. 教师主动添加词
4. 必要时少量其他候选，并标记来源待核验
```

## 预测拓展词

原则：

> 少而必要。

不得为了达到数量目标填词。

---

# 11. Proposal 分类原则

## 教材衔接

- 紧密衔接教材单元的核心主题、语言功能及主要语言项目；
- 优先使用教材核心词汇和句型；
- 不直接复述或模仿教材原有故事情节，通过新的角色、问题或情境实现语言迁移。

## 主题拓展

- 保留教材大主题，可离开教材原有活动和具体语言情境；
- 使用教材知识解决新的情境问题；
- 必须产生真实迁移，而非换皮。

## 跨学科提升

- 跨学科内容必须与 Unit 主题有自然、真实的联系；
- 可从自然科学、社会科学、人文、艺术等门类切入；
- 不为了体现“跨学科或跨文化”而进行生硬对比。

---

# 12. Proposal 不允许的行为

不得：

1. 假装 AI 自己知道教材原文；
2. 生成 8 个高度同质 Proposal；
3. 为了跨学科提升强行加入无关学科内容；
4. 把预测核心词当成正式核心词；
5. 在 Proposal 阶段写完整 8/12 页正文；
6. 偷偷改变教师提供的 Topic。

---


# 12A. 多选 Proposal 的项目拆分

确认：

> **一个 Project = 最终一本绘本。**

若教师一次选择多个 Proposal，系统自动拆分为多个独立绘本项目。

例如：

```text
Proposal A → Project A
Proposal C → Project C
Proposal F → Project F
```

各 Project 独立拥有：

- planned vocabulary；
- review words；
- drafts；
- validation；
- Final 状态。

UI 不使用 “fork” 术语，可显示：

> 已创建 3 个独立绘本项目。

---

# 12B. Unit 绘本类别配额

每个 Unit 最终必须形成恰好 7 本有效 Final（03语言项目收录标准：63 册 ÷ 9 Units）：

```text
总计：恰好 7
三类数量分配（2026-08-19 人工确认）：
教材衔接 2 / 主题拓展 3 / 跨学科提升 2
```

Proposal / Draft 可以超过 7 个并长期作为备选保存。

当某类别 Final 已达上限时：

> 仍可生成和编辑，但 Final Check 阻止新的超额 Final。


# 13. Review Word Recommendation

任务：

```text
RECOMMEND_REVIEW_WORDS
```

发生在：

> Proposal 选定后、正文生成前。

---

# 14. 复现词候选来源

Level 2 候选池来自：

> **本地存储中当前有效 Final 的 Level 2 核心词。**

Database 先提供：

```text
eligible review candidates
current recurrence progress
historical usage
```

LLM 只做：

> **语境适配排序**

而不是从模型记忆中自己发明复现词。

---

# 15. 复现词推荐原则

推荐数量：

```text
pool = 0   → 推荐 0 个
pool = 1–4 → 有几个推荐几个
pool >= 5  → 建议推荐 5–6 个
```

优先：

1. 与故事骨架自然兼容；
2. 当前累计复现不足；
3. 可以放入新语境；
4. 不引入额外不必要概念；
5. 不会迫使故事产生异常情节。

输出：

```text
lemma
reason
natural_insertion_point
current_progress
```

最终由教师确认。

---

# 16. Full Text Generation

任务：

```text
GENERATE_FULL_TEXT
```

每个选定 Proposal：

```text
2–3 versions
```

---

# 17. Full Text 必须输入

必须提供：

```text
selected proposal
planned core words
planned extension words
planned review words
confirmed core patterns
page_count
word_count target
generation orientation
teacher instructions
locked content if any
```

还需提供：

```text
Level 2 generation guidance
relevant RAG principles
```

---

# 18. Proposal Skeleton Fidelity

正文必须保持 Proposal 的：

```text
central premise
main causal chain
main problem / goal
resolution direction
```

可以调整：

- 节奏；
- 循环次数；
- 页面分配；
- 对话比例；
- 语言位置；
- 次要细节。

不可：

> 加入会改变故事核心因果链的重大新事件。

---

# 19. Full Text 页面要求

输出必须明确：

```text
Page 1
...
Page 8
```

或：

```text
Page 1
...
Page 12
```

每页：

```text
2–3 sentences target
```

整体：

```text
120–200 words
```

模型负责尽量满足，最终由 Validation 计算。

---

# 20. 核心句型生成

目标：

```text
1–2 patterns
```

每个 Pattern：

```text
自然重复约 3–5 次
```

通过替换：

- 名词；
- 动词；
- 地点；
- 形容词；

等 1–2 个元素形成变化。

禁止：

> 为重复而重复。

---

# 21. 核心词生成原则

计划核心词：

- 应实际进入正文；
- 位置应服务故事；
- 建议每个核心词自然出现约 3 次；
- 该频次不是硬性要求；
- 不应在无关句子中堆叠。

如果某核心词无法自然出现或无法达到建议频次：

> 返回 Warning，并建议教师手动输入其他核心词、修改故事、保留后重试或删除该计划核心词。

模型不得擅自删除或替换教师已确认的计划核心词。

---

# 22. 拓展词生成原则

计划拓展词：

- 非必须全部使用；
- 如果故事不需要，可在生成结果中标记“建议移除该计划词”；
- 不应为完成计划词表而增加新角色、新物体或新场景。

---

# 23. 复现词生成原则

计划复现词：

- 每个至少尝试自然出现一次；
- 复现必须有语义作用；
- 不要求单本内部反复多次；
- 不得因复现词改变核心故事逻辑。

若某复现词无法自然承载：

> 模型应返回 `review_word_fit_warning`

而不是硬塞进去。

---

# 24. Story / Language / Balanced

Demo V1 保留三个模式，默认：

```text
BALANCED
```

后续接入真实模型后，需要通过 Eval 检查三种模式是否能稳定产生可观察差异。

## STORY

优先：

- 情节自然；
- 因果；
- 节奏；
- 儿童趣味。

语言指标仍需满足基本要求，但允许更多 Warning。

## LANGUAGE

优先：

- 目标词句自然重复；
- 教材语言承载；
- 分级可控。

仍不得牺牲情节真实性。

## BALANCED

默认：

> 综合故事完整度与语言目标。

---

# 25. Version Diversity

同一 Proposal 下的 A/B/C 不应只是同义改写。

至少在部分维度上不同：

- 叙事节奏；
- 循环设计；
- 对话比例；
- 冲突展开；
- 结尾呈现。

但三版必须共享 Proposal 核心骨架。

---

# 26. Full Rewrite

任务：

```text
REWRITE_FULL_TEXT
```

输入必须包括：

- 当前 Draft；
- Proposal；
- 当前 planned vocabulary；
- core patterns；
- locked sentences；
- teacher instruction；
- latest validation issues。

输出：

> 新 Draft Version

不得原地覆盖旧 AI 版本。

---

# 27. Single Page Rewrite

任务：

```text
REWRITE_PAGE
```

输入：

- 全部故事上下文；
- 当前页；
- 前后页；
- locked sentences；
- 当前语言指标；
- teacher instruction。

只允许输出：

> 指定页面的新版本。

必须保持前后因果连贯。

---

# 28. Locked Sentence

任何 Rewrite Prompt 必须明确：

```text
LOCKED SENTENCES MUST REMAIN VERBATIM
```

LLM 无权：

- 同义改写；
- 调换内容；
- 删除。

若锁定内容与教师新要求冲突：

> 返回 conflict warning

而不是自行修改锁句。

---

# 29. Teacher Natural-Language Revision

教师可输入：

> “P3–P5 情节太平，增加一个意外，但不要增加新人物。”

模型必须识别：

```text
requested change
protected constraints
proposal skeleton
```

优先完成教师意图。

若要求会破坏：

- Proposal 核心骨架；
- 事实准确；
- 锁定内容；

应提示冲突。

---

# 30. Unclassified Vocabulary Suggestion

任务：

```text
SUGGEST_VOCAB_CLASSIFICATION
```

AI 可建议：

```text
CORE
EXTENSION_THEME
EXTENSION_CULTURAL
NON_TEACHING_CONTEXT
KNOWN / IGNORE
```

必须附：

```text
reason
confidence
```

但：

> teacher decides final role.

---

# 31. Historical Replacement Suggestion

任务：

```text
SUGGEST_REPLACEMENT
```

输入：

- 当前词；
- 历史使用；
- 当前句子 / 故事情境；
- Topic 语言资源。

AI 可以建议替换词。

必须保证：

- 不改变故事事实；
- 不显著提高难度；
- 不机械追求“完全没用过”。

---

# 32. Fact-sensitive Generation

若任务涉及事实性内容：

Prompt 必须明确：

```text
Do not invent specific factual claims.
Keep claims conservative.
Mark uncertain factual content for review.
```

如果系统后续提供可靠来源上下文：

> 只能基于所提供来源生成。

Demo V1 不要求 LLM 自行浏览互联网。

如果生成结果触发事实核验：

> 教师必须手动核验并填写备注后才能 Final。

未来如增加自动事实核验，需要新增独立 `Fact Retrieval / Fact Verification Workflow`，而不是只修改 Prompt。

---

# 33. 输出必须结构化

LLM 输出必须符合预定义 schema。

不得依赖：

> 从自然语言回答中用脆弱正则表达式猜字段。

Proposal、Full Text、分类建议均使用：

```text
structured JSON / validated schema
```

UI 再渲染为自然界面。

---

# 34. LLM Retry

若输出 schema 不合法：

```text
1. local schema repair if deterministic
2. one constrained retry
3. if still invalid → fail gracefully
```

不得无限自动重试。

---

# 35. Prompt 中不得塞入所有知识

每次只提供当前任务需要的：

- Database facts；
- RAG guidance；
- project state。

不要把：

- 全册教材词表全文；
- 全部 9 Unit；
- 全部历史绘本；
- 所有教研文档；

一次性塞入 Prompt。

---

# 36. LLM 不应做的事情

LLM 不得：

1. 决定数据库事实；
2. 修改原始教材数据；
3. 自行选择 Source of Truth；
4. 自行把 Warning 标为 resolved；
5. 直接写 Final；
6. 直接创建 recurrence event；
7. 直接判断“这个词一定不在教材范围”；
8. 用模型记忆补充未加载的教材内容；
9. 自动覆盖教师已确认的词汇角色；
10. 在没有提示的情况下改变 Proposal 核心故事。

---

# 37. Generation Quality Checklist

每次 Full Text 输出前，模型自检：

```text
□ 是否仍是同一个 Proposal？
□ 是否有清晰起因、发展和结尾？
□ 是否出现不自然的教材句型套用？
□ 是否为复现词制造了无关情节？
□ 拓展词是否真的必要？
□ 核心句型是否自然循环？
□ 是否存在明显中文直译？
□ 是否出现无法确认的事实性细节？
□ 是否符合 8/12 页结构？
```

这只是模型自检。

最终标准仍由 Validation Engine 决定。

---

# 38. Manual Check

1. **Story / Language / Balanced 实际区分度**：接入真实模型后需要 Eval；若差异不稳定再调 Prompt。  
2. **核心词 ×3 建议**：实测是否会诱发机械重复；必要时降低生成侧提示强度但保留 Warning。  
3. **自动事实核验**：Demo 暂不实现；未来需新增独立 Workflow。  
