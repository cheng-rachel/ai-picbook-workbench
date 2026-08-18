# 第一阶段后端与数据构建

本阶段仅实现 DOCX source extraction、structured intermediate、SQLite 静态/运行时基础结构、基础查询与自动化测试。未实现 UI、LLM、Proposal、正式 RAG、Final/Export 业务流程。

## 环境

- Python 3.10+
- 无第三方运行依赖

## 构建

```bash
python3 04scripts/rebuild_all.py
```

只执行 source validation：

```bash
python3 04scripts/validate_sources.py
```

只重建本地 RAG：

```bash
python3 04scripts/build_rag.py
```

运行测试：

```bash
python3 -m unittest discover -s 06tests -v
```

## 查询

```python
import sys
sys.path.insert(0, "05app")
from backend import ReferenceRepository

repo = ReferenceRepository()
topic = repo.get_topic(8)
rules = repo.get_level_rules(2)
entries = repo.lookup_textbook_entry("bike")
```

## Milestone 2：本地知识检索与服务层

普通 Teaching RAG 仅处理 `01–03` 中的解释性教研原则，使用无网络依赖的本地 TF-IDF 风格词项索引与 metadata filtering。教材词表、Unit 字段和教材额外例句不进入 RAG。

Workflow 使用受限接口：

- `LocalRagService.retrieve_for_proposal()`
- `retrieve_for_full_text()`
- `retrieve_for_vocab_classification()`
- `retrieve_for_review_recommendation()`
- `retrieve_for_rewrite()`

统一业务服务包括 `ReferenceDataService`、`HistoricalVocabularyService` 和 `ContextPreparationService`。它们将 Database Facts、RAG Guidance、Historical Context 分开返回，不调用 LLM。

`rebuild_all.py` 只清空并重建静态参考表；运行时表仅在不存在时创建，不会在 rebuild 中删除。

## 已补充的产品决策（2026-08-16）

- 正式 `book_number` 不在单本 Final 时分配；仅在整个 Level 2 的 63 册（9 Units × 7）全部定稿后统一分配。
- 统一分配后允许教师手动调整绘本顺序。
- 数据库继续区分 `EXTENSION_THEME` 与 `EXTENSION_CULTURAL`；导出展示暂合并为 `Words to know` 一列。

## Milestone 3：Proposal Generation

默认模型通过 backend 环境变量配置：

```bash
export MODEL_PROVIDER=openai_compatible
export MODEL_API_URL=https://your-provider.example/v1/chat/completions
export MODEL_API_KEY=your-secret
export DEFAULT_MODEL=your-default-model
export PROPOSAL_MODEL=your-proposal-model
export FULL_TEXT_MODEL=your-future-full-text-model
export REWRITE_MODEL=your-future-rewrite-model
```

密钥只从环境变量读取；`.env` 文件被 gitignore。M3 仅调用 `PROPOSAL_MODEL`，没有自动模型路由。

可选真实模型 smoke test：

```bash
python3 04scripts/smoke_test_proposals.py
```

未配置模型时，该命令安全跳过。普通单元测试全部使用 fake adapter，不访问网络。

代码入口：

```python
from backend import generate_proposals

result = generate_proposals(
    topic_id=8,
    count=8,
    teacher_input={"creative_instruction": "故事由行动体现坚持，不要说教。"},
)
```

成功结果只创建 `ACTIVE` Project、`GENERATED` Proposal 和 generation batch，不自动 Selected，也不写 Final 或正式动态词汇。

## Milestone 5：Finalization & Historical Recurrence

`backend.FinalizationWorkflow` 提供三个入口，全部无 LLM 依赖：

```python
from backend import FinalizationWorkflow

wf = FinalizationWorkflow(database_path=db_path)
wf.get_final_gate(project_id)     # read-only Gate 报告
wf.finalize_book(project_id)      # Gate 通过后单事务定稿
wf.unfinalize_book(book_id)       # 撤销定稿（失效统计，不删历史）
```

Final Gate 检查：最新 Validation 与当前正文一致且 BLOCKER=0、所有 Warning 已
ACKNOWLEDGED/RESOLVED、vocabulary confirmation 绑定当前 content hash 与 active
READY Plan、fact verification 完成、Unit 配额未超（总计 ≤7；三类分配 2026-08-19
人工确认为 教材衔接 2 / 主题拓展 3 / 跨学科提升 2，per-type 子配额同时生效）。

定稿事务写入口径：

- `final_book_vocabulary` 只写 CORE / EXTENSION / REVIEW 教学词；
  KNOWN_UNPLANNED 与 NON_TEACHING_CONTEXT 不进入 Final 快照与 recurrence。
- `recurrence_events` 只由正文中实际出现的 REVIEW 词产生（每书每词 1 条）；
  词第一次作为 CORE 定稿不计复现。
- `book_number` 定稿时留空，待整册统一分配。
- 撤销定稿将 Final 置非当前、recurrence 置 inactive、Project 回到 ACTIVE；
  重新定稿时旧记录通过 `superseded_by_book_id` 链接到新书。

回归测试：`06tests/test_m5_finalization.py`（FakeAdapter，无网络）。

## Milestone 6：Web App UI（已完成）

零依赖 stdlib server（`05app/webapp/`）：`queries.py` 只读拼装展示数据，
`server.py` 把 POST 动作 1:1 转发到既有 Workflow 方法，不重写业务规则。

```bash
python3 04scripts/run_webapp.py   # http://127.0.0.1:8765
```

已接入的 POST 动作：

- `/api/proposals/generate` → `ProposalWorkflow.generate_proposals`（LLM）
- `/api/proposals/manual` → `ProposalWorkflow.create_manual_proposal`：教师全手动
  录入方案（标题/类型/梗概必填，预测词可选），内部包装成单方案已定稿 Batch 并
  直接立项；该 Batch 不出现在筛选列表，Project 走正常后续流程。
- `/api/batch/establish` / `/api/batch/finalize` → 立项 / 结束筛选
- `/api/plan/prepare` / `/api/plan/confirm` → 词表计划创建・调整・确认
- `/api/candidates/generate`（LLM）/ `/api/candidate/select` → 候选正文生成 / 选为工作稿
- `/api/draft/autosave` → 正文分页编辑自动保存并重新校验
- `/api/vocabulary/confirm` / `/api/plan/revise` → 待确认词「非教学词」快照确认 /
  「值得教」晋升为词表草稿（随后走 `/api/plan/confirm`）
- `/api/issue/acknowledge` → Warning 逐条知悉
- `/api/fact-review` → 事实核验（`VERIFIED_BY_USER` 必须带备注）
- `/api/rewrite/preview`（LLM）/ `/api/rewrite/accept` / `/api/rewrite/cancel` →
  重写预览・接受・放弃；待决预览由 `queries.project_state` 暴露，刷新不丢
- `/api/final/finalize` / `/api/final/unfinalize` → 定稿 / 撤销定稿（M5）

展示层约定：校验条目按 `rule_key → 中文教师文案` 映射展示（`app.js` 的
`RULE_LABELS`），后端原始规则与 message 不变，原文作为次要信息保留展示。

回归测试：`06tests/test_m6_webapp.py`（FakeAdapter，无网络），
含「工作稿 → 词表处理 → 知悉 → 定稿 → 绘本库」的完整 API 链路用例。

## 正文格式约定：剧本式直接对话（2026-08-17）

人物话语从模型源头统一生成为剧本式直接对话，不做展示层字符串替换：

- Prompt 约束（`full_text_prompt.py`，生成与重写两套均含）：人物话语写成
  `Character Name: Dialogue`（如 `Big Elephant: You can't use your hands.`），
  每次发言独立一行；不使用引号，也不使用 `says X` / `X says` 等 reporting
  clause。旁白/动作/情境为无名字前缀的独立陈述句（如 `Little Monkey sits
  down.`），同一页可自然混排。
- 校验口径（`draft_validation.py`，RULE_VERSION `M4-V1.3`）：行首（或句末标点
  后）的 `Name:` 识别为说话人标签，属结构标记——标签词不计入总词数
  （120–200）与句长（≤10 词），标签本身不构成句子；对话正文按普通句子参与
  句数/句长/词数统计。标签中的人物名直接登记为 explicit character names，
  其在正文任意位置的出现均不进入教学词汇扫描，不会误报 NEEDS_REVIEW。
- Schema 不变：页面仍为 `{page_number, text}`，对话行与旁白行以换行区分，为
  后续排版阶段（气泡对话 vs 独立旁白）预留语义，本阶段仅文本层区分。

## M7 E2E 验收 bug 修复（2026-08-18）

- **手动方案的 AI 语言推荐立即可见**：推荐成功后前端随即调用
  `/api/plan/prepare` 生成 DRAFT 词表计划（`topic.html` 立项链路与
  `project.html` 重试按钮均如此），推荐的核心词/拓展词/句型直接以可编辑
  词表形式显示，教师调整确认后进入 READY；推荐或建表失败不影响已立项项目。
- **模型端点规范化与错误透传**（`model_adapter.py`）：
  `normalize_chat_completions_url` 允许 MODEL_API_URL 填完整
  chat/completions 地址或服务根路径（自动补全 `/chat/completions`）；
  服务商 HTTP 错误的消息包含状态码、模型名、端点与响应摘录，前端
  （`app.js`）把 `PROVIDER_ERROR` 映射为教师可读的配置检查提示。
  此前「生成候选正文 → HTTP 404」的根因即为配置的 API 地址缺少
  `/api/v3/chat/completions` 路径，服务商 404 被原样透出，易误判为路由缺失。
- 回归：`test_m7_model_config.py::ModelAdapterEndpointTests`（端点补全、
  错误详情）、`test_m6_webapp.py::test_provider_http_404_is_never_a_route_404`
  （服务商 404 与路由 404 的区分）。
