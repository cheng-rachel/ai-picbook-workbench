from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))

from backend.config import DOCS_DIR  # noqa: E402
from backend.database import build_database, connect  # noqa: E402
from backend.extractors import extract_all  # noqa: E402


class LegacyRuntimeMigrationTests(unittest.TestCase):
    def test_two_batch_container_projects_and_sixteen_proposals_are_migrated_losslessly(self):
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "legacy.sqlite"
            data = extract_all(DOCS_DIR)
            build_database(database_path, data)
            now = datetime.now(timezone.utc).isoformat()
            raw = sqlite3.connect(database_path)
            try:
                raw.execute("PRAGMA foreign_keys=OFF")
                raw.execute("DROP INDEX IF EXISTS idx_one_proposal_per_project")
                raw.execute("DROP INDEX IF EXISTS idx_proposal_batch_index")
                raw.execute("DROP TABLE proposals")
                raw.execute("DROP TABLE proposal_batches")
                raw.execute("""CREATE TABLE proposals (
                    proposal_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    proposal_batch_id TEXT,
                    proposal_index INTEGER,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(proposal_batch_id,proposal_index)
                )""")
                for batch_number in range(2):
                    project_id = f"legacy-project-{batch_number}"
                    batch_id = f"legacy-batch-{batch_number}"
                    raw.execute("""INSERT INTO projects
                        (project_id,topic_id,status,created_at,updated_at)
                        VALUES (?,'L2-T08','ACTIVE',?,?)""", (project_id, now, now))
                    for index in range(1, 9):
                        payload = {"title": f"Legacy {batch_number}-{index}",
                                   "book_type": "TEXTBOOK_SYNC"}
                        raw.execute("""INSERT INTO proposals VALUES
                            (?,?,?,?,?,'GENERATED',?,?)""",
                                    (f"legacy-proposal-{batch_number}-{index}", project_id,
                                     batch_id, index, json.dumps(payload), now, now))
                raw.commit()
            finally:
                raw.close()

            build_database(database_path, data)

            with connect(database_path) as db:
                self.assertEqual(16, db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0])
                self.assertEqual(16, db.execute(
                    "SELECT COUNT(*) FROM proposals WHERE project_id IS NULL AND status='GENERATED'"
                ).fetchone()[0])
                self.assertEqual(2, db.execute("SELECT COUNT(*) FROM proposal_batches").fetchone()[0])
                self.assertEqual(2, db.execute(
                    "SELECT COUNT(*) FROM projects WHERE status='ARCHIVED'"
                ).fetchone()[0])
                self.assertEqual(0, db.execute(
                    "SELECT COUNT(*) FROM projects WHERE status='ACTIVE'"
                ).fetchone()[0])
                self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
                project_column = next(row for row in db.execute("PRAGMA table_info(proposals)")
                                      if row[1] == "project_id")
                batch_column = next(row for row in db.execute("PRAGMA table_info(proposals)")
                                    if row[1] == "proposal_batch_id")
                self.assertEqual(0, project_column[3])
                self.assertEqual(1, batch_column[3])


if __name__ == "__main__":
    unittest.main()
