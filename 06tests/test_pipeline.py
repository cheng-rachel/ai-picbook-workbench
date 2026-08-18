from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))

from backend.database import build_database, connect  # noqa: E402
from backend.extractors import extract_all  # noqa: E402
from backend.repository import ReferenceRepository  # noqa: E402
from backend.validation import validate_sources  # noqa: E402


class SourceExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = extract_all(ROOT / "01docs")

    def test_level2_has_exactly_nine_complete_units(self):
        report = validate_sources(self.data)
        self.assertFalse(report["failures"], report)
        self.assertEqual(9, report["metrics"]["topics"])
        for topic in self.data["topics"]:
            self.assertTrue(topic["unit_title"])
            self.assertTrue(topic["theme"])
            self.assertTrue(topic["essential_question"])
            self.assertTrue(topic["grammar_text"])
            self.assertTrue(any(w["topic_id"] == topic["topic_id"] for w in self.data["textbook_words"]))
            self.assertTrue(any(s["topic_id"] == topic["topic_id"] for s in self.data["textbook_structures"]))

    def test_multiword_textbook_entry_is_preserved(self):
        topic8 = [w for w in self.data["textbook_words"] if w["topic_id"] == "L2-T08"]
        self.assertIn("city centre", [w["raw_entry"] for w in topic8])
        self.assertEqual("phrase", next(w["entry_type"] for w in topic8 if w["raw_entry"] == "city centre"))

    def test_slash_alternatives_are_kept_verbatim(self):
        entries = [w["raw_entry"] for w in self.data["textbook_words"]]
        self.assertIn("leaf/leaves", entries)
        self.assertIn("clean/brush your teeth", entries)

    def test_documented_source_conflicts_are_extracted(self):
        self.assertEqual("120-200", self.data["source_values"]["level_book_word_count"])
        self.assertEqual("3-5", self.data["source_values"]["core_word_frequency"])
        conflict_ids = {c["conflict_id"] for c in self.data["source_conflicts"]}
        self.assertIn("level2-core-word-frequency", conflict_ids)
        self.assertIn("level2-recurrence", conflict_ids)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.sqlite"
        self.data = extract_all(ROOT / "01docs")
        build_database(self.db_path, self.data)

    def tearDown(self):
        self.temp.cleanup()

    def test_database_counts_and_queries(self):
        repo = ReferenceRepository(self.db_path)
        topic = repo.get_topic(8)
        self.assertEqual("Around town", topic["unit_title"])
        self.assertEqual("A day trip; Places in town", topic["theme"])
        self.assertIn("city centre", topic["textbook_words"])
        self.assertTrue(topic["grammar_text"])
        self.assertEqual({"min": 120, "max": 200}, repo.get_level_rules(2)["book_word_count"]["effective_value"])
        # Textbook-wide lookup replaces the former curriculum vocabulary lookup.
        leaves = repo.lookup_textbook_entry("leaves")
        self.assertTrue(leaves)
        self.assertEqual("leaf/leaves", leaves[0]["raw_entry"])
        trips = repo.lookup_textbook_entry("Trips")
        self.assertTrue(trips)
        self.assertEqual("trip", trips[0]["raw_entry"])
        self.assertEqual("L2-T08", trips[0]["topic_id"])
        self.assertFalse(repo.lookup_textbook_entry("photosynthesis"))
        with connect(self.db_path) as db:
            self.assertEqual(9, db.execute("SELECT COUNT(*) FROM topics").fetchone()[0])
            tables = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("curriculum_entries", tables)
            self.assertNotIn("curriculum_variants", tables)
            self.assertEqual(1, db.execute("PRAGMA foreign_keys").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM final_book_vocabulary").fetchone()[0])
            self.assertNotIn("core", {row[1] for row in db.execute("PRAGMA table_info(textbook_words)")})
            examples = db.execute("SELECT COUNT(*) FROM textbook_examples").fetchone()[0]
            self.assertEqual(len(self.data["textbook_examples"]), examples)
            conflict = db.execute("SELECT variants_json FROM source_conflicts WHERE conflict_id='level2-core-word-frequency'").fetchone()[0]
            self.assertTrue(json.loads(conflict))
            override = db.execute("SELECT effective_value_json FROM product_overrides WHERE rule_key='level2.book_word_count'").fetchone()[0]
            self.assertEqual({"min": 120, "max": 200}, json.loads(override))
            book_number = db.execute("SELECT effective_value_json FROM product_overrides WHERE rule_key='book_number.allocation'").fetchone()[0]
            self.assertIn('"required_current_finals": 63', book_number)
            quota = db.execute("SELECT effective_value_json FROM product_overrides WHERE rule_key='topic_final_quota'").fetchone()[0]
            self.assertEqual(7, json.loads(quota)["total"])
            self.assertEqual({"TEXTBOOK_SYNC": 2, "THEME_EXTENSION": 3, "CROSS_CURRICULAR": 2},
                             json.loads(quota)["per_book_type"])
            export_rule = db.execute("SELECT effective_value_json FROM product_overrides WHERE rule_key='export.extension_words'").fetchone()[0]
            self.assertIn('"merge_theme_and_cultural": true', export_rule)
            scope_rule = db.execute("SELECT effective_value_json FROM product_overrides WHERE rule_key='vocabulary_source_scope'").fetchone()[0]
            self.assertEqual("power_up_2_textbook_words_only", json.loads(scope_rule))

    def test_static_rebuild_preserves_runtime_data(self):
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.db_path) as db:
            db.execute("INSERT INTO projects(project_id,topic_id,working_title,status,created_at,updated_at) VALUES (?,?,?,?,?,?)", ("runtime-sentinel", "L2-T01", "keep me", "ACTIVE", now, now))
        build_database(self.db_path, self.data)
        with connect(self.db_path) as db:
            row = db.execute("SELECT working_title FROM projects WHERE project_id='runtime-sentinel'").fetchone()
            self.assertEqual("keep me", row[0])


if __name__ == "__main__":
    unittest.main()
