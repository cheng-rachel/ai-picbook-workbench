# AGENTS.md — Power Up Picture Book Forge

## 1. Project Mission

Power Up Picture Book Forge（Power Up 绘编）是一个面向教师的本地 Web App，用于基于 Cambridge Power Up Second Edition（Power Up 2）教材与分级规则，完成：

> Proposal 生成 → 教师筛选 → 正文生成 → Validation → 教师修改 → Final → 历史词汇/复现统计 → 导出

它不是“一键生成整本绘本”的自动写作工具。

核心原则：

> **Proposal-first + Human-in-the-loop**

教师始终拥有 Proposal、词汇、正文和 Final 的最终决定权。

---

## 2. Source of Truth

实现前必须阅读：

```text
01docs/05product/
├── 01_product_workflow_v2.md
├── 02_data_mapping_v2.md
├── 03_data_dictionary_v2.md
├── 04_validation_rules_v2.md
├── 05_generation_rules_v2.md
└── 06_rag_mapping_v2.md
```

职责：

```text
01 Workflow          → 什么时候发生什么
02 Data Mapping      → 原始资料进入哪里
03 Data Dictionary   → 数据存什么、如何关联
04 Validation Rules  → 程序如何检查
05 Generation Rules  → LLM 如何生成
06 RAG Mapping       → 什么进入 RAG、何时检索
```

若实现细节与 Product Workflow 冲突：

> 优先保证 `01_product_workflow_v2.md` 的业务流程。

人工维护的原始教研资料位于 `01docs/` 下的 4 个 docx（绘本编写理念 / 分级标准 / 语言项目收录标准 / Level2教材依据），属于 Source of Truth。

SQLite、JSON、RAG index 均为派生数据，不得人工反向维护。

---

## 3. Required Architecture

Demo 必须实现为：

> **local browser-based Web App**

不是单个静态 HTML 原型。

推荐逻辑结构：

```text
Browser UI
    ↓
Workflow / Orchestrator
    ├── Database
    ├── RAG
    ├── Validation
    ├── LLM Service
    └── Export
```

技术栈可由 Codex 根据本地开发、依赖和维护成本选择。

不要为了技术展示引入不必要的复杂框架。

---

## 4. Resource Routing

最重要的架构约束：

> **Workflow / Orchestrator 决定何时调用 Database、RAG、Validation 和 LLM。**

LLM 不得自行决定：

- 是否查 Database；
- 是否查 RAG；
- 哪个来源优先；
- 是否写入 Final；
- 是否调用另一个模型。

权威结构化事实必须优先来自 Database，例如 Unit/Topic、Textbook Words（Power Up 2 全教材范围）、Textbook Structures、Historical Usage、Recurrence Count、Final Status。

RAG 只提供解释性教研原则。

---

## 5. Multi-model Design

Demo 第一版：

> **使用一个默认生成模型即可。**

但代码不得把业务逻辑与某一家模型 SDK 强绑定。

应保留统一模型接口，例如：

```text
generate(task_type, structured_input) -> structured_output
```

Workflow 通过配置决定某个任务使用哪个模型。

未来允许：

```text
PROPOSAL              → Model A
FULL_TEXT             → Model B
REWRITE               → Model B
VOCAB_CLASSIFICATION  → Model C / Default
```

例如未来可以：

> 中文 Proposal 使用更擅长中文故事策划的模型；  
> 英文正文与英文语言优化使用更擅长英语表达的模型。

模型之间不直接互相调用。

所有模型必须接受由 Workflow 组装的规范化输入，并返回统一 Schema。

Demo 不实现复杂自动 Model Routing。

---

## 6. Current Demo Scope

只实现：

```text
Level 2（教材：Cambridge Power Up 2）
9 Units
每个 Unit 最终 7 本 Final（全级共 63 本，依据 03语言项目收录标准「规划册数 63册」）
```

Unit Final 配额：

```text
总计：恰好 7
三类（教材衔接 / 主题拓展 / 跨学科提升）在 7 本中的数量分配：
Human Source 未规定 → HUMAN DECISION REQUIRED（当前只执行总量配额）
```

超过配额的 Proposal / Draft 可以长期保留，但不能继续 Final。

一个 Project：

> **对应最终一本绘本。**

多选 Proposal 后：

> 自动拆分为多个独立 Project。

---

## 7. Demo Simplifications

当前 Demo 明确不做：

- 正式账号系统；
- 云端多人协作；
- Draft 历史版本查询；
- Draft Diff / 回滚；
- 正式 Book Number 分配；
- multiword / 一词多义复杂统计；
- 自动联网事实核验；
- Level 1 / Level 3–6；
- 整本插图自动生成。

Draft：

> 实时 autosave 当前状态。

AI 全文 / 单页重写：

> 先生成预览；教师接受后覆盖 current draft。

正式 Book Number：

> Demo 不分配；正式产品待全册 63 本最终导出后统一分配。

---

## 8. Vocabulary Roles

Demo 使用：

```text
CORE
EXTENSION
REVIEW
NON_TEACHING_CONTEXT
UNCLASSIFIED
```

暂不区分主题拓展词 / 文化拓展词。

教材中的 multiword expression 原文必须保留，但 Demo 不做复杂拆分和正式统计口径判断。

首页词汇统计：

> 按 lemma 统计，暂未区分 multiword / 一词多义。

---

## 9. Recurrence

Level 2 复现候选池来自：

> **本地当前有效 Final 的 Level 2 CORE words。**

冷启动：

```text
pool = 0   → 不要求复现词
pool = 1–4 → 有几个推荐几个
pool >= 5  → 建议推荐 5–6 个
```

复现 3–5 次：

> 仅为跨 Final 绘本的建议目标，不是 Final 硬约束。

同一本书中一个 REVIEW 词出现多次：

> 仍只产生 1 个 book-level recurrence event。

---

## 10. Validation Philosophy

以下指标主要作为建议：

- 核心词约出现 3 次；
- 核心句型约重复 3–5 次；
- 跨书复现约 3–5 次；
- 非教学性情境词建议不超过 5 个。

未达到：

> Warning → 教师确认 → 可以继续。

不要为了消除 Warning 强行改坏故事。

Blocker 仅用于无法安全 Final 的问题，例如：

- 页面结构非法；
- 词表确认失效；
- 未处理的关键词汇身份问题；
- Fact Check 未完成；
- Topic Final 配额超限；
- Final 写入事务失败。

---

## 11. Fact Check

Demo 不实现自动 Fact Retrieval。

如果系统识别正文涉及需要核验的事实：

```text
REQUIRED
→ 教师人工核验
→ 填写 verification note
→ 教师确认
→ VERIFIED_BY_USER
```

未填写核验备注并确认：

> **Final Blocker**

---

## 12. Persistence

必须区分：

```text
Static Reference Data
Runtime / User Data
```

重新构建：

```text
docs/ → structured data / reference DB / RAG
```

不得删除或覆盖 Projects、current Drafts、Finals、manual review、recurrence history。

Draft 编辑采用实时本地保存。

Final 使用事务。

撤销 Final：

> 使旧 Final 失效并重新计算统计，不物理删除历史记录。

---

## 13. Development Order

Codex 应按以下顺序实现：

```text
1. Project skeleton
2. Source extraction / rebuild pipeline
3. Static Database
4. Data validation tests
5. Local RAG
6. Workflow / services
7. LLM integration
8. Validation Engine
9. Web UI
10. Final / history / export
```

不要先做漂亮 UI 再补数据逻辑。

第一阶段验收：

> 一个真实 Topic 能完整走完 Proposal → Draft → Validation → Final，且下一本绘本能够读取上一 Final 形成的历史词汇与复现候选。
