from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))

from backend.config import DOCS_DIR, ModelSettings  # noqa: E402
from backend.database import build_database, connect  # noqa: E402
from backend.extractors import extract_all  # noqa: E402
from backend.model_adapter import ModelResult  # noqa: E402
from backend.proposal_prompt import ProposalPromptAssembler, creative_diversification_plan  # noqa: E402
from backend.proposal_schema import CANONICAL_BOOK_TYPES, PROPOSAL_OUTPUT_SCHEMA  # noqa: E402
from backend.proposal_validation import ProposalValidator  # noqa: E402
from backend.proposal_workflow import ProposalWorkflow  # noqa: E402
from backend.services import ReferenceDataService  # noqa: E402


def proposal_payload(count: int = 8, duplicate: bool = False, invalid_type: bool = False) -> dict:
    settings = ["操场", "厨房", "公园", "图书角", "社区", "想象岛", "美术室", "运动场", "花园", "走廊"]
    problems = ["跳绳失败", "整理混乱", "路线不清", "合作分歧", "规则误解", "材料不足", "次数没数准", "动作不熟练", "计划改变", "伙伴需要帮助"]
    mechanisms = ["分步练习", "互相示范", "重新画图", "轮流尝试", "检查规则", "替换材料", "记录次数", "放慢动作", "调整步骤", "共同完成"]
    types = ["TEXTBOOK_SYNC", "THEME_EXTENSION", "CROSS_CURRICULAR"]
    proposals = []
    for i in range(count):
        title = "重复标题" if duplicate else f"多多的不同挑战{i + 1}"
        storyline = (f"多多来到{settings[i]}，很快遇到{problems[i]}。他和伙伴先看一看哪里不对，再选出第{i + 1}种简单办法。"
                     f"他们动手试过后发现还漏了一个小步骤，于是用{mechanisms[i]}把事情做好。多多笑着把这个办法用在新的小挑战里。")
        proposals.append({
            "proposal_index": i + 1, "title": title,
            "entry_point_cn": f"从{settings[i]}中的真实任务切入。", "storyline": storyline,
            "predicted_core_words": ["trip", "city centre"],
            "predicted_core_patterns": ["We have to stop.", "I went to the funfair."],
            "predicted_extension_words": ["farm"],
            "book_type": "BAD_TYPE" if invalid_type and i == 0 else types[i % 3],
            "plot_structure": f"任务出现—方案{i + 1}—失败转折—{mechanisms[i]}—完成",
            "potential_issues": "避免为了重复语言而增加无关情节。",
            "creative_highlight": f"用{mechanisms[i]}形成独特的解决机制。",
        })
    return {"proposals": proposals}


class FakeAdapter:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def generate(self, task_type, messages, output_schema, model_config):
        self.calls.append({"task_type": task_type, "messages": messages,
                           "output_schema": output_schema, "model_config": model_config})
        return self.results.pop(0)


class ProposalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "m3.sqlite"
        build_database(self.db, extract_all(DOCS_DIR))
        self.settings = ModelSettings("fake", "", None, "fake-default", "fake-proposal",
                                      "fake-full", "fake-rewrite", 1)

    def tearDown(self):
        self.tmp.cleanup()

    def workflow(self, adapter):
        return ProposalWorkflow(adapter=adapter, database_path=self.db, settings=self.settings)

    def test_model_adapter_is_mockable_and_default_count_is_eight(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(proposal_payload(), ensure_ascii=False))])
        result = self.workflow(fake).generate_proposals(8)
        self.assertTrue(result["ok"], result)
        self.assertEqual(8, len(result["proposals"]))
        self.assertEqual(1, len(fake.calls))
        self.assertEqual("PROPOSAL", fake.calls[0]["task_type"])
        self.assertEqual("fake-proposal", fake.calls[0]["model_config"]["model"])

    def test_context_and_prompt_layers_are_explicit_and_bounded(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(proposal_payload(), ensure_ascii=False))])
        result = self.workflow(fake).generate_proposals(8, teacher_input={"use": ["teamwork"], "avoid": ["危险动作"]})
        self.assertTrue(result["ok"])
        user_payload = json.loads(fake.calls[0]["messages"][1]["content"])
        self.assertIn("authoritative_database_facts", user_payload)
        self.assertIn("rag_guidance", user_payload)
        self.assertIn("historical_context", user_payload)
        self.assertIn("teacher_input", user_payload)
        self.assertEqual("A day trip; Places in town", user_payload["authoritative_database_facts"]["topic"]["theme"])
        self.assertNotIn("curriculum_entries", user_payload)
        self.assertLessEqual(len(user_payload["rag_guidance"]), 18)

    def test_prompt_calibration_requires_natural_storyline_diversity_and_simplicity(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(proposal_payload(), ensure_ascii=False))])
        result = self.workflow(fake).generate_proposals(8)
        self.assertTrue(result["ok"], result)
        messages = fake.calls[0]["messages"]
        system = messages[0]["content"]
        user_payload = json.loads(messages[1]["content"])
        rules = user_payload["proposal_generation_rules"]
        self.assertIn("continuous, natural Chinese prose", system)
        self.assertIn("forbidden_visible_section_labels", rules["storyline_display"])
        self.assertEqual([8, 12], rules["level_2_story_simplicity_budget"]["downstream_constraints"]["pages"])
        self.assertIn("不要求同时覆盖全部 Textbook Words", rules["textbook_language_scope"])
        planner = user_payload["hidden_creative_diversification_plan"]
        self.assertEqual(8, len(planner))
        self.assertTrue({"protagonist_type", "setting", "central_problem", "plot_driver",
                         "interaction_mode", "resolution_mechanism", "narrative_form",
                         "imaginative_level"}.issubset(planner[0]))
        self.assertEqual(8, len({item["protagonist_type"] for item in planner}))
        self.assertEqual(8, len({item["setting"] for item in planner}))

    def test_template_style_storyline_is_rejected(self):
        payload = proposal_payload()
        payload["proposals"][0]["storyline"] = (
            "起因：多多第一次拿起跳绳。核心问题：绳子总碰到鞋子。发展：他观察朋友的脚步，慢慢找到节奏。"
            "转折：他决定把动作放慢。结尾：多多连续跳了五下，开心地和朋友击掌。"
        )
        fake = FakeAdapter([ModelResult(True, json.dumps(payload, ensure_ascii=False))])
        result = self.workflow(fake).generate_proposals(8)
        self.assertEqual("VALIDATION_FAILED", result["error_code"])
        codes = {issue["code"] for issue in result["validation"]["issues"]}
        self.assertIn("TEMPLATE_STYLE_STORYLINE", codes)

    def test_generated_rows_are_runtime_only_and_not_selected_or_final(self):
        with connect(self.db) as db:
            static_before = db.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        fake = FakeAdapter([ModelResult(True, json.dumps(proposal_payload(), ensure_ascii=False))])
        result = self.workflow(fake).generate_proposals(8)
        with connect(self.db) as db:
            self.assertEqual(static_before, db.execute("SELECT COUNT(*) FROM topics").fetchone()[0])
            self.assertEqual(8, db.execute("SELECT COUNT(*) FROM proposals WHERE status='GENERATED'").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM proposals WHERE status='SELECTED'").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM final_books").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM projects").fetchone()[0])
            batch = db.execute("SELECT * FROM proposal_batches WHERE proposal_batch_id=?",
                               (result["proposal_batch_id"],)).fetchone()
            self.assertEqual("L2-T08", batch["topic_id"])
            self.assertEqual(8, batch["original_proposal_count"])
            self.assertIsNotNone(batch["evaluation_json"])
            self.assertEqual(8, db.execute(
                "SELECT COUNT(*) FROM proposals WHERE proposal_batch_id=? AND project_id IS NULL",
                (result["proposal_batch_id"],)).fetchone()[0])

    def test_multi_select_establishes_independent_projects_then_finalize_discards_unselected(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(proposal_payload(), ensure_ascii=False))])
        workflow = self.workflow(fake)
        generated = workflow.generate_proposals(8)
        selected_ids = [item["proposal_id"] for item in generated["proposals"][:3]]
        established = workflow.establish_projects_from_proposals(
            generated["proposal_batch_id"], selected_ids)
        self.assertTrue(established["ok"], established)
        self.assertEqual(3, established["established_count"])
        with connect(self.db) as db:
            self.assertEqual(3, db.execute(
                "SELECT COUNT(*) FROM projects WHERE status='ACTIVE' AND selected_proposal_id IS NOT NULL"
            ).fetchone()[0])
            self.assertEqual(5, db.execute(
                "SELECT COUNT(*) FROM proposals WHERE proposal_batch_id=? AND project_id IS NULL",
                (generated["proposal_batch_id"],)).fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM pre_generation_plans").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM draft_versions").fetchone()[0])
        finalized = workflow.finalize_proposal_batch_selection(generated["proposal_batch_id"])
        self.assertEqual(3, finalized["selected_count"])
        self.assertEqual(5, finalized["discarded_count"])
        with connect(self.db) as db:
            self.assertEqual(3, db.execute(
                "SELECT COUNT(*) FROM proposals WHERE proposal_batch_id=?",
                (generated["proposal_batch_id"],)).fetchone()[0])
            audit = db.execute(
                "SELECT original_proposal_count,selected_count,discarded_count,selection_finalized_at "
                "FROM proposal_batches WHERE proposal_batch_id=?",
                (generated["proposal_batch_id"],),
            ).fetchone()
            self.assertEqual((8, 3, 5), tuple(audit[:3]))
            self.assertIsNotNone(audit["selection_finalized_at"])

    def test_existing_project_does_not_block_a_new_batch(self):
        fake = FakeAdapter([
            ModelResult(True, json.dumps(proposal_payload(), ensure_ascii=False)),
            ModelResult(True, json.dumps(proposal_payload(), ensure_ascii=False)),
        ])
        workflow = self.workflow(fake)
        first = workflow.generate_proposals(8)
        workflow.establish_projects_from_proposals(
            first["proposal_batch_id"], [first["proposals"][0]["proposal_id"]])
        second = workflow.generate_proposals(8)
        self.assertTrue(second["ok"], second)
        self.assertNotEqual(first["proposal_batch_id"], second["proposal_batch_id"])
        with connect(self.db) as db:
            self.assertEqual(2, db.execute("SELECT COUNT(*) FROM proposal_batches").fetchone()[0])
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM projects WHERE status='ACTIVE'").fetchone()[0])

    def test_predicted_vocabulary_has_database_source_lookup(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(proposal_payload(), ensure_ascii=False))])
        result = self.workflow(fake).generate_proposals(8)
        checks = result["proposals"][0]["predicted_vocabulary_validation"]
        # "trip" is a current-unit textbook word; "farm" belongs to another unit
        # (Unit 1), so it resolves through the whole-textbook scope.
        self.assertEqual("TEXTBOOK", next(x["source_status"] for x in checks if x["raw_form"] == "trip"))
        self.assertEqual("TEXTBOOK_SCOPE", next(x["source_status"] for x in checks if x["raw_form"] == "farm"))

    def test_invalid_json_retries_once_then_succeeds(self):
        fake = FakeAdapter([ModelResult(True, "not json"),
                            ModelResult(True, json.dumps(proposal_payload(), ensure_ascii=False))])
        result = self.workflow(fake).generate_proposals(8)
        self.assertTrue(result["ok"])
        self.assertEqual(2, result["attempts"])
        self.assertEqual(2, len(fake.calls))

    def test_retry_is_bounded_and_returns_invalid_schema(self):
        fake = FakeAdapter([ModelResult(True, "bad"), ModelResult(True, "still bad")])
        result = self.workflow(fake).generate_proposals(8)
        self.assertFalse(result["ok"])
        self.assertEqual("INVALID_SCHEMA", result["error_code"])
        self.assertEqual(2, len(fake.calls))

    def test_provider_error_is_structured_without_retry(self):
        fake = FakeAdapter([ModelResult(False, error_code="PROVIDER_ERROR", error_message="offline")])
        result = self.workflow(fake).generate_proposals(8)
        self.assertEqual("PROVIDER_ERROR", result["error_code"])
        self.assertEqual(1, len(fake.calls))

    def test_invalid_book_type_fails_validation_and_is_not_saved(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(proposal_payload(invalid_type=True), ensure_ascii=False))])
        result = self.workflow(fake).generate_proposals(8)
        self.assertEqual("VALIDATION_FAILED", result["error_code"])
        with connect(self.db) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0])

    def manual_input(self) -> dict:
        return {"title": "The Helping Broom", "book_type": "TEXTBOOK_SYNC",
                "storyline": "Amy wants to clean the classroom. Friends take turns and help."}

    def test_language_recommendation_fills_manual_proposal_predictions(self):
        fake = FakeAdapter([ModelResult(True, json.dumps({
            "predicted_core_words": ["clean", "help", "clean", "  "],
            "predicted_extension_words": ["broom"],
            "predicted_core_patterns": ["Let me help you.", "Can you help?", "Extra one"],
        }, ensure_ascii=False))])
        workflow = self.workflow(fake)
        created = workflow.create_manual_proposal(8, self.manual_input())
        self.assertTrue(created["ok"], created)
        result = workflow.recommend_language_for_proposal(created["proposal_id"])
        self.assertTrue(result["ok"], result)
        self.assertEqual(["clean", "help"], result["predicted_core_words"])
        self.assertEqual(["Let me help you.", "Can you help?"],
                         result["predicted_core_patterns"])
        self.assertEqual("PROPOSAL", fake.calls[0]["task_type"])
        prompt_payload = json.loads(fake.calls[0]["messages"][1]["content"])
        self.assertEqual("RECOMMEND_LANGUAGE_PLAN", prompt_payload["task"]["type"])
        self.assertEqual("The Helping Broom",
                         prompt_payload["teacher_proposal"]["title"])
        with connect(self.db) as db:
            payload = json.loads(db.execute(
                "SELECT payload_json FROM proposals WHERE proposal_id=?",
                (created["proposal_id"],)).fetchone()[0])
        self.assertEqual(["clean", "help"], payload["predicted_core_words"])
        self.assertEqual(["broom"], payload["predicted_extension_words"])
        # The teacher's story itself is never rewritten.
        self.assertEqual(self.manual_input()["storyline"], payload["storyline"])
        self.assertEqual("MANUAL", payload["source"])

    def test_language_recommendation_failure_leaves_proposal_and_project_intact(self):
        fake = FakeAdapter([ModelResult(False, error_code="MODEL_NOT_CONFIGURED",
                                        error_message="MODEL_API_KEY or MODEL_API_URL is not configured")])
        workflow = self.workflow(fake)
        created = workflow.create_manual_proposal(8, self.manual_input())
        result = workflow.recommend_language_for_proposal(created["proposal_id"])
        self.assertFalse(result["ok"])
        self.assertEqual("MODEL_NOT_CONFIGURED", result["error_code"])
        with connect(self.db) as db:
            payload = json.loads(db.execute(
                "SELECT payload_json FROM proposals WHERE proposal_id=?",
                (created["proposal_id"],)).fetchone()[0])
            project_status = db.execute(
                "SELECT status FROM projects WHERE project_id=?",
                (created["project_id"],)).fetchone()[0]
        self.assertEqual([], payload["predicted_core_words"])
        self.assertEqual("ACTIVE", project_status)

    def test_language_recommendation_invalid_schema_retries_then_fails_cleanly(self):
        fake = FakeAdapter([ModelResult(True, "not json"),
                            ModelResult(True, json.dumps({"predicted_core_words": []}))])
        workflow = self.workflow(fake)
        created = workflow.create_manual_proposal(8, self.manual_input())
        result = workflow.recommend_language_for_proposal(created["proposal_id"])
        self.assertFalse(result["ok"])
        self.assertEqual("INVALID_SCHEMA", result["error_code"])
        self.assertEqual(2, result["attempts"])
        missing = workflow.recommend_language_for_proposal("missing-proposal")
        self.assertEqual("PROPOSAL_NOT_FOUND", missing["error_code"])

    def test_diversity_check_detects_obvious_duplicates(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(proposal_payload(duplicate=True), ensure_ascii=False))])
        result = self.workflow(fake).generate_proposals(8)
        self.assertEqual("VALIDATION_FAILED", result["error_code"])
        codes = {issue["code"] for issue in result["validation"]["issues"]}
        self.assertIn("DUPLICATED_TITLES", codes)

    def test_diversity_check_detects_same_story_with_different_titles(self):
        payload = proposal_payload()
        repeated = payload["proposals"][0]["storyline"]
        repeated_plot = payload["proposals"][0]["plot_structure"]
        for proposal in payload["proposals"]:
            proposal["storyline"] = repeated
            proposal["plot_structure"] = repeated_plot
        fake = FakeAdapter([ModelResult(True, json.dumps(payload, ensure_ascii=False))])
        result = self.workflow(fake).generate_proposals(8)
        codes = {issue["code"] for issue in result["validation"]["issues"]}
        self.assertIn("LOW_DIVERSITY", codes)

    def test_repeated_mechanism_signals_are_info_only(self):
        payload = proposal_payload()
        variations = [
            "小鹿在操场上练跳绳，总跟不上绳子的节奏。它把动作放慢，请小兔帮忙拍手打节拍。小鹿终于找到适合自己的速度，轻轻跳过绳子。它没有参加比赛，只把新节奏展示给朋友看。",
            "乐乐在校园运动角拍球，球总从手边跑开。他先观察同学的动作，再放慢速度，请同伴帮忙捡球。乐乐找到稳定节奏后，能让球连续弹回手边。他把场地让给下一位同学。",
            "玩具熊在学校操场学做简单运动，却总比音乐快一步。它请发条小鸟帮忙数拍子，然后放慢动作找到节奏。音乐再次响起时，玩具熊稳稳完成了动作。两个玩具安静地坐下来休息。",
        ]
        for index, storyline in enumerate(variations):
            payload["proposals"][index]["storyline"] = storyline
            payload["proposals"][index]["plot_structure"] = "节奏不合—观察—请求帮助—放慢动作—找到节奏"
        fake = FakeAdapter([ModelResult(True, json.dumps(payload, ensure_ascii=False))])
        result = self.workflow(fake).generate_proposals(8)
        self.assertTrue(result["ok"], result)
        signals = result["validation"]["metrics"]["diversity_signals"]
        self.assertTrue(signals["repeated_plot_driver"])
        self.assertTrue(signals["repeated_resolution_mechanism"])
        self.assertTrue(signals["repeated_setting_pattern"])
        info_issues = [issue for issue in result["validation"]["issues"]
                       if issue.get("severity") == "INFO"]
        self.assertTrue(info_issues)


class ConfigurationTests(unittest.TestCase):
    def test_canonical_book_types_and_schema(self):
        self.assertEqual({"TEXTBOOK_SYNC", "THEME_EXTENSION", "CROSS_CURRICULAR"}, CANONICAL_BOOK_TYPES)
        self.assertEqual(["proposals"], PROPOSAL_OUTPUT_SCHEMA["required"])

    def test_diversification_plan_supports_six_to_ten_without_fixed_book_type_quota(self):
        plan = creative_diversification_plan(10)
        self.assertEqual(10, len(plan))
        self.assertNotIn("book_type", plan[0])
        self.assertEqual(10, len({item["central_problem"] for item in plan}))
        self.assertEqual(10, len({item["resolution_mechanism"] for item in plan}))

    def test_no_api_key_literal_in_backend_source(self):
        for path in (ROOT / "05app" / "backend").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"sk-[A-Za-z0-9]{12,}", str(path))


if __name__ == "__main__":
    unittest.main()
