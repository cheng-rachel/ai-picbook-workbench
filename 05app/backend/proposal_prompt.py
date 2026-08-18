"""Proposal-only prompt assembly with explicit trust boundaries."""

from __future__ import annotations

import json

from .proposal_schema import LANGUAGE_RECOMMENDATION_SCHEMA, PROPOSAL_OUTPUT_SCHEMA


def creative_diversification_plan(count: int) -> list[dict]:
    dimensions = {
        "protagonist_type": ["人类儿童", "动物", "植物", "玩具", "外星人", "小精灵", "拟人化物体", "亲子组合", "儿童搭档", "幻想生物"],
        "setting": ["学校", "家里", "公园", "森林", "花园", "河边或海边", "水底", "天空或云朵", "太空", "简洁想象世界"],
        "central_problem": ["还没找到合适的方法", "工具不合适", "需要等待合适时机", "看不懂伙伴的办法", "太着急而跳过关键一步", "害怕第一次尝试", "旧办法在新场景失效", "需要请求帮助", "小误会阻碍合作", "只差一个小步骤"],
        "plot_driver": ["动作的可见变化", "寻找合适工具", "观察与模仿", "简短对话", "等待与再出发", "节奏变化", "一次小选择", "角色互助", "轻悬念", "想象性的单一规则"],
        "interaction_mode": ["独自探索", "同伴合作", "角色与物体互动", "观察另一个角色", "请求帮助", "轮流示范", "安静陪伴", "误会后沟通", "共同游戏", "与环境互动"],
        "resolution_mechanism": ["放慢下来找到合适的方式", "换一种工具", "观察后改一个做法", "等一等再做", "主动请求帮助", "把目标变小", "让伙伴示范", "改变站位或距离", "用游戏化办法", "接受一点点进步"],
        "narrative_form": ["自然线性梗概", "温和循环", "对话推动", "视觉递进", "轻悬念", "一日片段", "反差发现", "角色互换", "重复中变化", "开放式小问题"],
        "imaginative_level": ["现实日常", "现实中的轻想象", "拟人化", "温和奇幻", "想象世界", "现实日常", "拟人化", "温和奇幻", "现实中的轻想象", "想象世界"],
    }
    keys = list(dimensions)
    return [{key: dimensions[key][(index + offset) % len(dimensions[key])]
             for offset, key in enumerate(keys)} for index in range(count)]


class ProposalPromptAssembler:
    def assemble(self, context: dict, teacher_input: dict, count: int) -> list[dict]:
        if not 6 <= count <= 10:
            raise ValueError("Proposal count must be between 6 and 10")
        rag_results = context["rag_guidance"]["results"]
        payload = {
            "task": {"type": "GENERATE_PROPOSALS", "count": count,
                     "language": "故事逻辑主要使用中文；预测词和句型使用英语"},
            "authoritative_database_facts": context["authoritative_database_facts"],
            "rag_guidance": [{key: item[key] for key in
                              ("text", "source_document", "rule_type", "verification_status", "priority")}
                             for item in rag_results],
            "historical_context": context["historical_context"],
            "teacher_input": teacher_input,
            "hidden_creative_diversification_plan": creative_diversification_plan(count),
            "proposal_generation_rules": {
                "storyline_display": {
                    "format": "连续、自然、可直接给教师阅读的中文故事梗概",
                    "internal_logic_only": ["setup", "problem_or_goal", "development", "main_action_or_small_turn", "resolution"],
                    "forbidden_visible_section_labels": ["起因", "发展", "核心问题", "主要循环", "转折", "解决", "结尾"],
                    "instruction": "不要显示结构标签或写成故事分析报告；用自然句子呈现完整因果和结尾。",
                },
                "topic_concept_divergence": {
                    "textbook_role": "Textbook Words、Structures、Examples 只用于确定 Topic、核心语言和教学边界；教材例句、对话和情境不是故事情节模板，不需要模仿、延续或近义改写。",
                    "instruction": "先从 Theme 和 Essential Question 提炼本 Topic 的上位概念，再围绕这个概念本身的不同侧面发散出真正不同的故事前提（发散层级示意：概念如何产生、为什么需要它、如何理解它、被打破或不适用时会怎样、在不同情境中的样子等；这只说明发散的抽象层级，不是可选项清单）。整批 Proposal 不应都停留在教材例句所描绘的同一活动或情境上。",
                },
                "diversity": {
                    "instruction": "先按隐藏计划发散，再写 Proposal；计划是创意起点，不是固定槽位或硬配额。整批避免重复主角类型、场景模式、问题机制和解决机制；同批方案之间的差异应体现在情节机制上（问题如何产生、如何推进、如何化解各不相同）。",
                    "avoid": "不能只换人物、地点、道具、运动项目或措辞，而保留同一故事机制；也不能整批沿用教材例句或对话中的同一活动情境做近义改写。",
                },
                "level_2_story_simplicity_budget": {
                    "downstream_constraints": {"pages": [8, 12], "total_words": "120–200", "sentences_per_page": "2–3"},
                    "prefer": ["一个清晰主角或主角组合", "一个核心问题", "一条主要情节线", "一个主要行动循环", "一个简单变化或小转折", "一个清楚结尾", "一句话可以说清 premise", "简单 premise + 可重复行动 + 清楚视觉变化"],
                    "avoid": ["多个规则系统", "多个地点连续切换", "多组人物", "多项并列任务", "多层文化背景", "多次复杂转折", "需要大量旁白解释的设定"],
                },
                "textbook_language_scope": "每个 Proposal 只需聚焦教材词汇中一小组自然相关的词；不要求同时覆盖全部 Textbook Words。预测句型应是可复用的结构框架（含可替换成分），并落在本 Unit Grammar 范围内。",
                "value_theme_variation": "涉及成长、习惯、合作、责任等价值主题时，通过具体行动和情节自然体现；不要默认使用失败—再试—失败—再试—成功的固定弧线，也不要由成人直接说教。",
            },
            "required_output_schema": PROPOSAL_OUTPUT_SCHEMA,
        }
        system = (
            "You are the proposal-generation component inside Power Up Picture Book Forge (textbook basis: "
            "Cambridge Power Up 2). Workflow has already selected all resources. AUTHORITATIVE DATABASE FACTS are "
            "the only textbook facts. RAG GUIDANCE contains teaching principles, not textbook facts. Never invent or "
            "modify Unit Title, Theme, Essential Question, Textbook Words, Grammar scope, Cross-curricular focus, "
            "Level rules, historical usage, or status. "
            "Return JSON only. Do not generate full page text, select a proposal, write SQL, or create Final data. "
            "Write each storyline as continuous, natural Chinese prose for a teacher, with a complete simple causal arc. "
            "Never show section labels such as 起因、发展、核心问题、主要循环、转折、解决、结尾 inside storyline. "
            "Keep each Level 2 premise simple enough for 8 or 12 pages and 120–200 words. Do not force all Textbook "
            "Words into one proposal. Follow the hidden diversification plan as inspiration, not as visible output. "
            "The unit's textbook content defines language scope and teaching boundaries only; it is never a plot "
            "template. Derive premises from the unit's core concept (Theme and Essential Question) and explore "
            "genuinely different facets of that concept with different plot mechanisms; do not echo one scenario "
            "across the batch. For CROSS_CURRICULAR proposals, extend naturally from the unit's Cross-curricular "
            "focus without forcing comparisons. Predicted core patterns must be reusable sentence frames within the "
            "unit's Grammar scope. "
            "Predicted core words are candidates only; extension words use the single EXTENSION concept."
        )
        return [{"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


class LanguagePlanRecommendationAssembler:
    """Suggest CORE/EXTENSION words and patterns for a teacher-authored Proposal.

    The teacher's story is authoritative input and must never be rewritten or
    judged; the output is suggestions only and still passes through the normal
    Pre-generation Plan teacher confirmation.
    """

    def assemble(self, context: dict, proposal: dict) -> list[dict]:
        rag_results = context["rag_guidance"]["results"]
        payload = {
            "task": {"type": "RECOMMEND_LANGUAGE_PLAN",
                     "language": "词汇与句型使用英语"},
            "authoritative_database_facts": context["authoritative_database_facts"],
            "rag_guidance": [{key: item[key] for key in
                              ("text", "source_document", "rule_type", "verification_status", "priority")}
                             for item in rag_results],
            "historical_context": context["historical_context"],
            "teacher_proposal": {key: proposal.get(key, "") for key in
                                 ("title", "entry_point_cn", "storyline", "book_type")},
            "recommendation_rules": {
                "goal": "只为这份教师撰写的故事方案推荐教学语言；不评价、不改写、不续写故事本身。",
                "predicted_core_words": "2–4 个，优先来自本 Unit 教材词汇，其次是 Power Up 2 其他单元中与故事情节强相关的已学词；单词或短语均可。",
                "predicted_extension_words": "0–4 个，仅在故事确实需要时推荐，宁少勿多。",
                "predicted_core_patterns": "1–2 个，应是可复用的句型框架（含可替换成分），落在本 Unit Grammar 范围内并与故事情节匹配。",
                "constraints": "语言需适合 Level 2 分级绘本（8/12 页、全书 120–200 词、每句不超过 10 词）。这些只是建议值，教师会在词表计划中逐项确认。",
            },
            "required_output_schema": LANGUAGE_RECOMMENDATION_SCHEMA,
        }
        system = (
            "You are the language-recommendation component inside Power Up Picture Book Forge (textbook basis: "
            "Cambridge Power Up 2). "
            "The teacher wrote this story Proposal; treat it as fixed input and never rewrite, extend, or judge it. "
            "AUTHORITATIVE DATABASE FACTS are the only textbook facts. Recommend teaching language only: "
            "predicted_core_words, predicted_extension_words, predicted_core_patterns. Prefer words from this unit's "
            "textbook scope and reusable sentence frames within the unit's Grammar scope, and keep everything "
            "achievable for Level 2 readers. These are suggestions for the teacher's Pre-generation Plan, not final "
            "decisions. Return JSON only, matching the required schema exactly."
        )
        return [{"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
