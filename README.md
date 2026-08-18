# AI Picture Book/Graded Reading Workbench
AI 分级阅读内容生产工作台｜Product Demo

An AI-assisted workflow for graded English reading content generation, validation, human review, and language recurrence tracking.

本项目是一个**面向K12英语教研与内容编写人员的本地 Web App工作台demo**，

它尝试解决的不是“让 AI 自动写一本绘本”，而是将**教材依据、分级标准、生成式 AI、规则校验与教师专业判断**组织成一个可追踪的内容生产流程，使 AI 生成真正进入教研工作流。

它把「Cambridge Power Up 2 教材依据 + 分级阅读规则 + 本地 RAG + LLM 创作 + 程序校验 + 教师人工决策」组织成可追踪的分级绘本生产流程。核心理念：**LLM 负责创作，程序负责约束，教师负责决策**。

当前版本覆盖 第二版Power Up Level 2 全部 9 个 Unit。

---

## 1. Overview

传统的 AI 内容生成通常依赖反复对话和 Prompt 调整：

```text
提出要求
→ AI 生成
→ 人工发现问题
→ 修改 Prompt
→ 再生成
→ 人工检查
```

这种方式能够快速获得文本，但进入规模化教研生产后仍存在几个问题：

- 教材要求与分级标准容易在多轮生成中丢失；
- 核心词、句型和复现要求需要人工反复核对；
- AI 输出中的语言、事实和难度问题缺少稳定的检查机制；
- 教师修改难以沉淀为后续内容生产可利用的数据；
- 一本内容完成后，与下一本内容之间缺少语言学习上的连续性。

本项目将这些要求拆解为**结构化数据、生成约束、程序校验和 Human-in-the-loop 决策节点**，形成完整的内容生产工作流。

---

## 2. Demo Scope

当前 Demo 以 **Cambridge Power Up Second Edition / Power Up 2** 为教材锚点，展示 Level 2 的分级阅读内容生产流程。

```text
Level 2
9 Units
7 books / Unit
63 books planned
```

教材提供 Topic、Vocabulary、Grammar、Cross-curricular 等课程约束；分级标准进一步控制篇幅、词汇、句型、语篇与阅读难度。

Demo 的重点不是复现教材内容，而是展示：

> **如何将 Curriculum Constraints 与 Grading Constraints 转化为 AI 可执行、程序可检查、教师可干预的内容生产 Workflow。**

---

## 3. Product Workflow

一篇分级阅读内容从选题到定稿经历以下流程：

```text
Topic
  ↓
Proposal
  ↓
Language Plan
  ↓
Full-text Generation
  ↓
Validation
  ↓
Human Review / Rewrite
  ↓
Finalization
  ↓
Historical Recurrence
```

### ① Topic

选择教材 Unit，读取对应的主题、语言项目和跨学科依据。

系统首先确定“这一单元学什么”，而不是直接要求模型自由生成故事。

### ② Proposal

AI 根据教材依据、分级要求和内容类型生成多个差异化故事方案。

教师选择具有教学价值和故事潜力的方案，再进入正式编写。

### ③ Language Plan

在正文生成前确定本篇的语言计划，包括：

- **CORE** — 本篇重点教学词汇
- **EXTENSION** — 为主题或故事表达需要引入的拓展词
- **REVIEW** — 前序内容中需要再次复现的词汇
- **Core Patterns** — 本篇重点语言结构

Language Plan 将开放式故事创作转化为具有明确语言约束的生成任务。

### ④ Full-text Generation

AI 根据选定 Proposal 与 Language Plan 生成候选正文。

教师选择候选版本作为 Current Draft，并可继续人工编辑。

### ⑤ Validation

程序对正文进行规则校验，例如：

- 总词数是否符合级别要求；
- CORE / EXTENSION 是否实际出现；
- 核心词是否达到建议复现次数；
- 是否出现未规划词汇；
- 核心句型是否得到合理复现；
- 是否触发事实核验要求；
- 是否满足 Final 条件。

对于能够确定性判断的问题，优先交由程序完成，而不是让 LLM 自己判断自己的输出是否合格。

### ⑥ Human Review & Rewrite

Validation 不直接替代教师决策。

教师可以：

- 直接编辑正文；
- 将未规划词加入教学词表；
- 将必要词判断为非教学语境词；
- 对单页或全文调用 AI Rewrite；
- 接受或拒绝 AI 修改；
- 对 Warning 和事实问题进行人工确认。

### ⑦ Finalization

只有满足必要规则并完成教师确认后，作品才能进入 Final。

Final 不只是“保存最终文本”，还会将本篇的教学词汇和语言使用情况写入历史数据。

### ⑧ Historical Recurrence

下一篇内容生成时，系统能够读取此前已经 Final 的内容，推荐需要再次出现的 REVIEW words。

```text
Book A Final
     ↓
Historical Vocabulary Data
     ↓
Book B Language Plan
     ↓
Book B Generation
```

单篇内容生产由此形成跨书的语言学习连续性。

---

## 4. Key Product Design

### Curriculum × Grading Constraints

系统同时处理两类约束：

```text
Curriculum Constraints
Topic / Vocabulary / Grammar / Cross-curricular
                    ×
Grading Constraints
Length / Vocabulary Load / Patterns / Discourse / Reading Difficulty
                    ↓
              Language Plan
```

教材决定**“学什么”**，分级标准决定**“以什么难度学习”**。

两类约束共同形成单篇内容的 Language Plan，再进入生成环节。

### Human-in-the-loop

AI 不直接决定最终教学内容。

关键节点保留教师专业判断，包括：

```text
Proposal Selection
Language Planning
Vocabulary Decision
Draft Selection
Rewrite Acceptance
Fact Verification
Final Approval
```

系统的目标不是移除教师，而是减少重复性生产和机械检查，把真正需要专业判断的问题留给教师。

### Rule-based Validation

对于词数、词汇出现次数、计划词覆盖、Final 条件等能够明确计算的问题，优先使用程序规则进行检查。

LLM 主要承担开放式生成、方案发散和语言改写任务。

### Local RAG

教研原则和生成规则被整理为本地知识资源。

不同生成任务根据需要检索相关规则，而不是将全部教研要求重复塞入每一次 Prompt。

### Historical Recurrence

Final 内容进入历史数据后，可以影响后续 Language Plan 和 REVIEW 推荐，使不同绘本之间形成可追踪的词汇复现关系。

---

## 5. Demo Content Types

当前 Demo 将分级阅读内容分为三类：

| Type | Purpose |
| --- | --- |
| **教材衔接** | 围绕教材核心主题和语言功能创设新的故事情境，实现语言迁移与巩固 |
| **主题拓展** | 从教材主题进一步拓展儿童生活经验、行为方式、情感态度或社会认知 |
| **跨学科提升** | 将单元主题与自然科学、社会科学、人文或艺术等内容建立自然联系 |

Power Up 2 Demo 当前规划：

```text
2 教材衔接
+ 3 主题拓展
+ 2 跨学科提升
= 7 books / Unit
```

---

## 6. System Architecture

```text
Human-maintained Teaching Sources
              ↓
       Structured Data
              ↓
       Local RAG Index
              ↓
┌─────────────────────────────┐
│       Workflow Engine       │
│                             │
│  LLM Generation             │
│  Validation Engine          │
│  Human Review               │
│  Finalization               │
│  Historical Recurrence      │
└─────────────────────────────┘
              ↓
           SQLite
              ↓
         Local Web App
```

项目采用本地 Web App 形式运行。

模型负责生成内容；Workflow 决定模型**何时被调用、获得哪些上下文，以及生成结果满足什么条件后才能进入下一阶段**。

---

## 7. Repository Structure

```text
ai-picbook-workbench/
│
├── README.md
├── ai-picbook-workbench.command
│
├── 01docs/              # Human-maintained teaching & product sources
├── 02data/              # Structured data and local database
├── 03rag/               # Processed RAG resources and local index
├── 04scripts/           # Build / validation / launch scripts
├── 05app/               # Backend and Web App
├── 06tests/             # Regression and workflow tests
│
├── HANDOVER.md          # Developer handover
├── IMPLEMENTATION.md    # Implementation notes
└── pyproject.toml
```

---

## 8. Quick Start

### Requirements

- Python 3
- macOS recommended for the provided `.command` launcher
- An OpenAI-compatible model API is optional

The Demo can be browsed without an API key.

AI generation and rewrite functions require model configuration.

### Launch

On macOS, double-click:

```text
ai-picbook-workbench.command
```

or run it from Terminal.

The application starts a local Web App at:

```text
http://127.0.0.1:8765/
```

### Model Configuration

Model configuration can be completed inside the Web App.

Required:

```text
MODEL_PROVIDER
MODEL_API_URL
MODEL_API_KEY
DEFAULT_MODEL
```

Optional task-level models:

```text
PROPOSAL_MODEL
FULL_TEXT_MODEL
REWRITE_MODEL
```

If task-level models are not specified, the application uses `DEFAULT_MODEL`.

Real credentials are stored locally and are not committed to the repository.

See `.env.example` for the configuration template.

---

## 9. Data & Privacy

The project is designed as a local Demo:

- model credentials remain local;
- `.env.local` is excluded from Git;
- the Web App and SQLite database run locally;
- API calls are made only when AI generation or rewrite functions are explicitly used.

No API key is included in this repository.

---

## 10. Current Scope

This repository is a **Product Demo**, not a production SaaS platform.

Current scope focuses on demonstrating:

- AI-assisted graded-reading content generation;
- curriculum and grading constraint orchestration;
- structured Language Planning;
- rule-based Validation;
- Human-in-the-loop editorial control;
- local RAG;
- cross-book vocabulary recurrence.

It currently does not aim to provide:

- student-facing reading applications;
- user accounts or multi-user collaboration;
- cloud deployment;
- automated online fact verification;
- production publishing or copyright-management systems.

---

## 11. Design Principle

The central product idea is:

> **AI generates possibilities; rules enforce explicit constraints; teachers make pedagogical decisions.**

AI 适合处理开放式生成、方案发散和语言改写；

程序适合处理能够明确计算和验证的规则；

教师负责需要教学经验、语言判断和内容决策的关键节点。

因此，这个工作台的目标不是简单地“用 AI 写绘本”，而是：

> **把聊天式、依赖个人 Prompt 的内容生成过程，转化为可约束、可验证、可人工干预、可沉淀历史数据的 AI 教研生产 Workflow。**

---

## 12. Current Status

Current Demo:

```text
Power Up 2
Level 2
9 Units

End-to-end workflow implemented
Local Web App
Configurable LLM API
Structured Language Plan
Rule-based Validation
Human Review / Rewrite
Finalization
Historical Recurrence
```

For implementation details, data mapping, validation rules and developer handover, see:

```text
01docs/05product/
HANDOVER.md
IMPLEMENTATION.md
```
