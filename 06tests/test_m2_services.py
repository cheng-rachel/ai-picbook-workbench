from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))

from backend.config import DATABASE_PATH, DOCS_DIR, RAG_INDEX_PATH, RAG_PROCESSED_DIR  # noqa: E402
from backend.context_service import ContextPreparationService  # noqa: E402
from backend.rag_builder import RAG_SOURCES, build_rag, build_rag_safely  # noqa: E402
from backend.rag_service import LocalRagService, TASK_RULE_TYPES  # noqa: E402
from backend.services import HistoricalVocabularyService, ReferenceDataService  # noqa: E402


class RagBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_rag(DOCS_DIR, RAG_PROCESSED_DIR, RAG_INDEX_PATH)
        cls.chunks = [json.loads(line) for line in
                      (RAG_PROCESSED_DIR / "teaching_guidance.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_all_chunks_have_required_metadata(self):
        required = {"chunk_id", "source_document", "source_section", "source_heading", "text",
                    "rule_type", "level_scope", "book_type_scope", "topic_scope", "task_scope",
                    "verification_status", "priority", "source_hash"}
        self.assertTrue(self.chunks)
        for chunk in self.chunks:
            self.assertFalse(required - chunk.keys(), chunk)
            self.assertTrue(chunk["text"].strip())

    def test_forbidden_exact_fact_sources_are_not_indexed(self):
        sources = {chunk["source_document"] for chunk in self.chunks}
        self.assertEqual(set(RAG_SOURCES.values()), sources)
        # Exact-fact topic/word source stays out of RAG (database lookups only).
        self.assertNotIn("04Level2教材依据.docx", sources)

    def test_numeric_conflict_chunks_are_non_authoritative(self):
        # Raw numeric planning rows (63册 / 120–200 / 8+4 / 3–5) must never be
        # runtime-authoritative; effective values come from product overrides.
        conflicting = [c for c in self.chunks if "63册" in c["text"] or "每册阅读量" in c.get("source_heading", "")]
        self.assertTrue(conflicting)
        self.assertTrue(all(c["non_authoritative_for_runtime_numeric_rules"] for c in conflicting))

    def test_source_hash_change_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            docs = base / "01docs"
            processed = base / "processed"
            index = base / "index" / "local_index.json"
            docs.mkdir()
            for filename in RAG_SOURCES.values():
                shutil.copy2(DOCS_DIR / filename, docs / filename)
            build_rag(docs, processed, index)
            service = LocalRagService(docs, processed, index)
            self.assertEqual("READY", service.status().state)
            with (docs / "03语言项目收录标准.docx").open("ab") as handle:
                handle.write(b"stale")
            status = service.status()
            self.assertEqual("STALE", status.state)
            self.assertIn("03语言项目收录标准.docx", status.source_files)

    def test_empty_retrieval_is_distinct_from_failure(self):
        ready_empty = LocalRagService()._retrieve("VOCAB_CLASSIFICATION", 2, {"NO_SUCH_RULE_TYPE"})
        self.assertEqual("READY", ready_empty["status"]["state"])
        self.assertEqual([], ready_empty["results"])
        with tempfile.TemporaryDirectory() as tmp:
            missing = LocalRagService(DOCS_DIR, Path(tmp) / "processed", Path(tmp) / "index.json")
            failed = missing.retrieve_for_proposal(2, "THEME_EXTENSION")
            self.assertEqual("MISSING", failed["status"]["state"])
            self.assertEqual([], failed["results"])

    def test_source_build_failure_is_structured(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            result = build_rag_safely(base / "missing-docs", base / "processed", base / "index.json")
            self.assertEqual("BUILD_FAILED", result["state"])
            self.assertFalse(result["available"])
            self.assertIn("01绘本编写理念.docx", result["source_files"])

    def test_rag_rebuild_does_not_touch_runtime_database(self):
        before = sha256(DATABASE_PATH.read_bytes()).hexdigest()
        build_rag(DOCS_DIR, RAG_PROCESSED_DIR, RAG_INDEX_PATH)
        after = sha256(DATABASE_PATH.read_bytes()).hexdigest()
        self.assertEqual(before, after)


class RetrievalScopeTests(unittest.TestCase):
    def test_proposal_retrieval_scope(self):
        response = LocalRagService().retrieve_for_proposal(2, "THEME_EXTENSION")
        self.assertEqual("READY", response["status"]["state"])
        self.assertTrue(response["results"])
        for item in response["results"]:
            self.assertIn(item["rule_type"], TASK_RULE_TYPES["PROPOSAL"])
            self.assertIn(item["level_scope"], ("ALL", "LEVEL_2"))
            self.assertIn(item["book_type_scope"], ("ALL", "THEME_EXTENSION"))

    def test_full_text_retrieval_scope(self):
        response = LocalRagService().retrieve_for_full_text(2, "TEXTBOOK_SYNC")
        self.assertTrue(response["results"])
        for item in response["results"]:
            self.assertIn(item["rule_type"], TASK_RULE_TYPES["FULL_TEXT"])
            self.assertTrue("FULL_TEXT" in item["task_scope"] or "ALL" in item["task_scope"])


class BackendServiceTests(unittest.TestCase):
    def setUp(self):
        self.reference = ReferenceDataService(DATABASE_PATH)
        self.history = HistoricalVocabularyService(DATABASE_PATH)

    def test_topic_reference_and_examples_come_from_database(self):
        topic = self.reference.get_topic_reference(8)
        self.assertEqual("Around town", topic["unit_title"])
        self.assertEqual("A day trip; Places in town", topic["theme"])
        # Power Up 2 source has no extra textbook example sentences.
        self.assertEqual([], self.reference.get_textbook_examples(8))

    def test_textbook_lookup(self):
        result = self.reference.lookup_textbook_entry("leaves")[0]
        self.assertEqual("leaf/leaves", result["raw_entry"])
        self.assertEqual("L2-T01", result["topic_id"])

    def test_history_and_review_cold_start(self):
        self.assertEqual([], self.history.get_historical_vocab_usage("red"))
        pool = self.history.get_review_candidates(2, 8)
        self.assertEqual(0, pool["pool_size"])
        self.assertEqual([], pool["candidates"])
        self.assertFalse(pool["warning_required"])

    def test_context_keeps_three_sources_separate_and_database_authoritative(self):
        context = ContextPreparationService().prepare_proposal_context(8, "THEME_EXTENSION")
        self.assertEqual({"authoritative_database_facts", "rag_guidance", "historical_context"}, set(context))
        facts = context["authoritative_database_facts"]
        self.assertEqual({"min": 120, "max": 200}, facts["level_rules"]["book_word_count"]["effective_value"])
        self.assertEqual("A day trip; Places in town", facts["topic"]["theme"])
        self.assertEqual("READY", context["rag_guidance"]["status"]["state"])


if __name__ == "__main__":
    unittest.main()
