/* Shared helpers for the Demo UI. Display logic only; no business rules. */

async function fetchJSON(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || "请求失败");
  return data;
}

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    if (response.status === 404 && data.error_code === "NOT_FOUND") {
      throw new Error("服务端没有这个操作接口：Web 服务可能仍在运行旧版本，请关闭旧服务窗口并重新启动后重试");
    }
    if (data.error_code === "MODEL_NOT_CONFIGURED" ||
        /MODEL_API_KEY|MODEL_API_URL/.test(data.message || "")) {
      throw new Error("AI 生成功能需要配置模型服务后才能使用。当前未检测到 API 配置，" +
        "你仍可以正常浏览已有内容。如需使用 AI 生成，请先在「模型配置」页面" +
        "填写你自己的 API 服务信息。");
    }
    if (data.error_code === "PROVIDER_ERROR") {
      throw new Error("模型服务调用失败，本次操作未执行。请到「模型配置」检查 " +
        "API 地址和各模型名称是否正确（地址需指向 chat/completions 接口，" +
        "只填到服务根路径时系统会自动补全）。技术详情：" +
        (data.message || "未知错误"));
    }
    throw new Error(data.message || "操作失败，请重试");
  }
  return data;
}

/* Disable a button while an async action runs, showing progress text. */
async function withBusy(button, busyText, action) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = busyText;
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function esc(value) {
  return String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function qs(name) {
  return new URLSearchParams(location.search).get(name) || "";
}

function toast(message) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  document.body.appendChild(node);
  // Longer messages stay a little longer so teachers can finish reading.
  setTimeout(() => node.remove(), Math.min(9000, Math.max(2200, message.length * 80)));
}

/* Skeleton placeholder: real workflow wiring arrives in Step 3. */
function pendingAction() {
  toast("该操作将在 Step 3 接入真实 Workflow");
}

const BOOK_TYPE_LABELS = {
  TEXTBOOK_SYNC: "教材衔接", THEME_EXTENSION: "主题拓展", CROSS_CURRICULAR: "跨学科提升",
  ALL: "不限类型",
};
const ROLE_LABELS = { CORE: "核心词", EXTENSION: "拓展词", REVIEW: "复现词" };
const SOURCE_LABELS = {
  TEXTBOOK: "本单元教材", TEXTBOOK_SCOPE: "教材其他单元", TEACHER_ADDED: "教师添加",
  UNRESOLVED: "未收录",
};
const SOURCE_BADGES = {
  TEXTBOOK: "blue", TEXTBOOK_SCOPE: "blue", TEACHER_ADDED: "gray", UNRESOLVED: "amber",
};
const STAGE_LABELS = {
  PLAN: "待确认词表", PLAN_READY: "词表已确认，待生成正文", CANDIDATES: "候选比较中",
  DRAFT: "工作稿修改中", FINAL: "已定稿",
};
const PROJECT_STAGE_BADGES = {
  PLAN: "amber", PLAN_READY: "blue", CANDIDATES: "blue", DRAFT: "blue", FINAL: "green",
};
const ORIENTATION_LABELS = {
  STORY: "故事优先", LANGUAGE: "语言优先", BALANCED: "均衡",
};

function sourceBadge(status) {
  return `<span class="badge ${SOURCE_BADGES[status] || "gray"}">${SOURCE_LABELS[status] || esc(status)}</span>`;
}

function stageBar(stage) {
  const steps = [
    { key: "PROPOSAL", label: "① 方案" },
    { key: "PLAN", label: "② 词表计划" },
    { key: "CANDIDATES", label: "③ 候选正文" },
    { key: "DRAFT", label: "④ 工作稿与校验" },
    { key: "FINAL", label: "⑤ 定稿" },
  ];
  const order = { PLAN: 1, PLAN_READY: 2, CANDIDATES: 2, DRAFT: 3, FINAL: 4 };
  const now = order[stage] ?? 1;
  return `<div class="stagebar">` + steps.map((step, index) => {
    const cls = index < now ? "done" : index === now ? "now" : "";
    return `<span class="step ${cls}">${step.label}</span>`;
  }).join("") + `</div>`;
}

function severityLabel(severity) {
  return { BLOCKER: "必须处理", WARNING: "提醒", INFO: "参考" }[severity] || severity;
}

/* 展示层映射：rule_key → 教师中文文案。后端原始规则与 message 不变。 */
const RULE_LABELS = {
  "VAL-PAGE-001": "页数或页码与词表计划不一致",
  "VAL-BLANK-PAGE-001": "存在空白页",
  "VAL-PAGE-SENT-001": "本页句数偏离建议（每页 2–3 句）",
  "VAL-SENT-LEN-001": "有句子超过 10 个词，低年级读起来偏长",
  "VAL-WORDCOUNT-001": "全书词量偏离建议范围（120–200 词）",
  "VAL-HISTORY-001": "该词与历史定稿绘本中的教学角色冲突",
  "VAL-VOCAB-SOURCE-001": "该词不在 Power Up 2 教材词汇范围内",
  "VAL-CORE-001": "计划核心词没有在正文中出现",
  "VAL-CORE-FREQ-001": "核心词出现次数偏离目标（约 3–5 次）",
  "VAL-EXT-001": "计划拓展词没有在正文中出现",
  "VAL-REVIEW-001": "计划复现词没有在正文中出现",
  "VAL-EXT-COUNT-001": "拓展词数量超过建议上限（4 个）",
  "VAL-NON-TEACHING-001": "非教学词数量超过建议上限（5 个）",
  "VAL-REVIEW-COUNT-001": "复现词计划数量偏离建议（5–6 个）",
  "VAL-UNCLASSIFIED-001": "正文中有词需要老师先确认如何处理（见下方“本书词汇”）",
  "VAL-PATTERN-001": "核心句型数量偏离建议（1–2 个）",
  "VAL-PATTERN-002": "核心句型出现次数偏离建议（约 3–5 次）",
};

function issueScopeLabel(scope) {
  if (!scope) return "";
  if (scope.type === "page") return `第 ${scope.page_number} 页`;
  if (scope.type === "sentence") return `第 ${scope.page_number} 页第 ${scope.sentence_number} 句`;
  if (scope.type === "word") return `词 “${esc(scope.word)}”`;
  if (scope.type === "pattern") return `句型 “${esc(scope.pattern)}”`;
  return "";
}

function issueText(issue) {
  const label = RULE_LABELS[issue.rule_key];
  const scope = issueScopeLabel(issue.scope);
  if (!label) return esc(issue.message);
  return `${scope ? scope + "：" : ""}${label}`;
}
