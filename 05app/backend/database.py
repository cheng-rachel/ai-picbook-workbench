from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

STATIC_TABLES = [
    "textbook_examples",
    "textbook_structures", "textbook_words", "topics", "book_types",
    "level_rules", "levels", "product_overrides", "source_conflicts", "source_documents",
]


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _table_columns(db: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row]:
    return {row[1]: row for row in db.execute(f"PRAGMA table_info({table})")}


def _downstream_count(db: sqlite3.Connection, project_id: str) -> int:
    total = 0
    for table in ("pre_generation_plans", "full_text_candidates", "draft_versions", "final_books"):
        total += db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,)
        ).fetchone()[0]
    return total


def _migrate_proposal_lifecycle(db: sqlite3.Connection) -> None:
    """Migrate the pre-batch M3 runtime without fabricating missing audit payloads."""
    columns = _table_columns(db, "proposals")
    project_is_required = bool(columns["project_id"][3])
    batch_is_required = bool(columns["proposal_batch_id"][3])
    if not project_is_required and batch_is_required:
        return

    now = "legacy-migration"
    missing_batch_rows = db.execute(
        "SELECT proposal_id,project_id FROM proposals WHERE proposal_batch_id IS NULL"
    ).fetchall()
    for row in missing_batch_rows:
        db.execute(
            "UPDATE proposals SET proposal_batch_id=? WHERE proposal_id=?",
            (f"legacy-proposal-batch-{row['project_id'] or uuid4().hex}", row["proposal_id"]),
        )

    batches = db.execute(
        """SELECT p.proposal_batch_id,COUNT(*) AS proposal_count,
                  MIN(p.created_at) AS created_at,
                  SUM(CASE WHEN p.status='SELECTED' THEN 1 ELSE 0 END) AS selected_count,
                  GROUP_CONCAT(DISTINCT pr.topic_id) AS topic_ids
           FROM proposals p LEFT JOIN projects pr ON pr.project_id=p.project_id
           GROUP BY p.proposal_batch_id"""
    ).fetchall()
    for batch in batches:
        topic_ids = [value for value in (batch["topic_ids"] or "").split(",") if value]
        if len(topic_ids) != 1:
            raise ValueError(
                f"Cannot migrate Proposal Batch {batch['proposal_batch_id']}: Topic is ambiguous"
            )
        book_types = set()
        for payload_row in db.execute(
            "SELECT payload_json FROM proposals WHERE proposal_batch_id=?",
            (batch["proposal_batch_id"],),
        ):
            try:
                value = json.loads(payload_row[0]).get("book_type")
            except (json.JSONDecodeError, AttributeError):
                value = None
            if value:
                book_types.add(value)
        target_book_type = next(iter(book_types)) if len(book_types) == 1 else "ALL"
        db.execute(
            """INSERT OR IGNORE INTO proposal_batches
               (proposal_batch_id,topic_id,target_book_type,teacher_input_json,
                original_proposal_count,evaluation_json,selected_count,discarded_count,
                selection_finalized_at,created_at)
               VALUES (?,?,?,?,?,NULL,?,0,NULL,?)""",
            (batch["proposal_batch_id"], topic_ids[0], target_book_type, "{}",
             batch["proposal_count"], batch["selected_count"], batch["created_at"] or now),
        )

    proposal_overrides: dict[str, tuple[str | None, str]] = {}
    for project in db.execute("SELECT * FROM projects").fetchall():
        proposals = db.execute(
            "SELECT proposal_id,status FROM proposals WHERE project_id=?", (project["project_id"],)
        ).fetchall()
        if not proposals:
            continue
        selected_id = project["selected_proposal_id"]
        if selected_id:
            if selected_id not in {row["proposal_id"] for row in proposals}:
                raise ValueError(f"Project {project['project_id']} has an invalid selected Proposal")
            for row in proposals:
                proposal_overrides[row["proposal_id"]] = (
                    project["project_id"] if row["proposal_id"] == selected_id else None,
                    "SELECTED" if row["proposal_id"] == selected_id else "GENERATED",
                )
        elif not project["current_draft_id"] and _downstream_count(db, project["project_id"]) == 0:
            for row in proposals:
                proposal_overrides[row["proposal_id"]] = (None, "GENERATED")
            db.execute(
                "UPDATE projects SET status='ARCHIVED' WHERE project_id=?", (project["project_id"],)
            )
        else:
            raise ValueError(
                f"Cannot migrate Project {project['project_id']} without a selected Proposal"
            )

    db.execute("DROP INDEX IF EXISTS idx_proposal_batch_index")
    db.execute("""CREATE TABLE proposals_new (
        proposal_id TEXT PRIMARY KEY,
        project_id TEXT REFERENCES projects(project_id),
        proposal_batch_id TEXT NOT NULL REFERENCES proposal_batches(proposal_batch_id),
        proposal_index INTEGER,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(proposal_batch_id,proposal_index)
    )""")
    for row in db.execute("SELECT * FROM proposals").fetchall():
        project_id, status = proposal_overrides.get(
            row["proposal_id"], (row["project_id"], row["status"])
        )
        db.execute("""INSERT INTO proposals_new
            (proposal_id,project_id,proposal_batch_id,proposal_index,payload_json,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
                   (row["proposal_id"], project_id, row["proposal_batch_id"],
                    row["proposal_index"], row["payload_json"], status,
                    row["created_at"], row["updated_at"]))
    db.execute("DROP TABLE proposals")
    db.execute("ALTER TABLE proposals_new RENAME TO proposals")


def build_database(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with connect(path) as db:
        db.executescript(schema)
        db.execute("PRAGMA foreign_keys = OFF")
        _migrate_proposal_lifecycle(db)
        db.commit()
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_one_proposal_per_project
                      ON proposals(project_id) WHERE project_id IS NOT NULL""")
        final_columns = {row[1] for row in db.execute("PRAGMA table_info(final_books)")}
        if "book_number" not in final_columns:
            db.execute("ALTER TABLE final_books ADD COLUMN book_number INTEGER")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_current_book_number ON final_books(book_number) WHERE is_current=1 AND book_number IS NOT NULL")
        proposal_columns = set(_table_columns(db, "proposals"))
        if "proposal_batch_id" not in proposal_columns:
            db.execute("ALTER TABLE proposals ADD COLUMN proposal_batch_id TEXT")
        if "proposal_index" not in proposal_columns:
            db.execute("ALTER TABLE proposals ADD COLUMN proposal_index INTEGER")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_proposal_batch_index ON proposals(proposal_batch_id,proposal_index) WHERE proposal_batch_id IS NOT NULL")
        pattern_columns = set(_table_columns(db, "planned_patterns"))
        if "teacher_confirmed" not in pattern_columns:
            db.execute("ALTER TABLE planned_patterns ADD COLUMN teacher_confirmed INTEGER NOT NULL DEFAULT 0 CHECK(teacher_confirmed IN (0,1))")
        observation_columns = set(_table_columns(db, "draft_vocab_observations"))
        if "classification_state" not in observation_columns:
            db.execute("""ALTER TABLE draft_vocab_observations ADD COLUMN classification_state TEXT
                          NOT NULL DEFAULT 'NEEDS_REVIEW'
                          CHECK(classification_state IN ('PLANNED','KNOWN_UNPLANNED','NEEDS_REVIEW'))""")
        confirmation_columns = set(_table_columns(db, "vocabulary_confirmations"))
        if "plan_id" not in confirmation_columns:
            db.execute("ALTER TABLE vocabulary_confirmations ADD COLUMN plan_id TEXT REFERENCES pre_generation_plans(plan_id)")
        draft_columns = {row[1] for row in db.execute("PRAGMA table_info(draft_versions)")}
        for column, definition in (
            ("source_candidate_id", "TEXT REFERENCES full_text_candidates(candidate_id)"),
            ("generation_orientation", "TEXT"),
            ("page_count_target", "INTEGER"),
        ):
            if column not in draft_columns:
                db.execute(f"ALTER TABLE draft_versions ADD COLUMN {column} {definition}")
        page_columns = {row[1] for row in db.execute("PRAGMA table_info(draft_pages)")}
        for column in ("created_at", "updated_at"):
            if column not in page_columns:
                db.execute(f"ALTER TABLE draft_pages ADD COLUMN {column} TEXT")
        # Power Up 2 unit fields for databases created before the relocation.
        topic_columns = set(_table_columns(db, "topics"))
        for column in ("unit_title", "grammar_text", "cross_curricular_text", "literature_text"):
            if column not in topic_columns:
                db.execute(f"ALTER TABLE topics ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        # Keep runtime rows intact. Temporarily defer FK checks because runtime rows
        # may refer to static Topic IDs that are reinserted in this same transaction.
        db.execute("PRAGMA defer_foreign_keys = ON")
        for table in STATIC_TABLES:
            db.execute(f"DELETE FROM {table}")
        for row in data["source_documents"]:
            db.execute("INSERT INTO source_documents VALUES (?,?,?,?,?,?,?)", tuple(row.values()))
        db.execute("INSERT INTO levels VALUES (?,?,?,?)", tuple(data["level"].values()))
        for row in data["level_rules"]:
            db.execute("INSERT INTO level_rules VALUES (?,?,?,?,?,?,?,?,?,?)", (
                row["level_rule_id"], row["level_id"], row["rule_key"], row["raw_value"],
                json.dumps(row["effective_value"], ensure_ascii=False), row["value_type"],
                row["rule_strength"], row["source_document_id"], row["source_section"], row["note"]))
        for row in data["book_types"]:
            db.execute("INSERT INTO book_types(code,display_name_zh,core_positioning) VALUES (?,?,?)", tuple(row.values()))
        for row in data["topics"]:
            db.execute("""INSERT INTO topics
                (topic_id,level_id,semester,unit_number,topic_number,unit_title,theme,
                 essential_question,grammar_text,cross_curricular_text,literature_text,
                 source_document_id,active)
                VALUES (:topic_id,:level_id,:semester,:unit_number,:topic_number,:unit_title,
                        :theme,:essential_question,:grammar_text,:cross_curricular_text,
                        :literature_text,:source_document_id,:active)""", row)
        for row in data["textbook_words"]:
            db.execute("INSERT INTO textbook_words(topic_id,raw_entry,normalized_entry,entry_type,sequence_no,source_document_id) VALUES (?,?,?,?,?,?)", tuple(row.values()))
        for row in data["textbook_structures"]:
            db.execute("INSERT INTO textbook_structures(topic_id,raw_structure,normalized_pattern,sequence_no,source_document_id) VALUES (?,?,?,?,?)", tuple(row.values()))
        for row in data["textbook_examples"]:
            db.execute("INSERT INTO textbook_examples(topic_id,raw_sentence,source_section,sequence_no,verification_status,source_document_id,note) VALUES (?,?,?,?,?,?,?)", tuple(row.values()))
        for row in data["product_overrides"]:
            db.execute("INSERT INTO product_overrides(rule_key,effective_value_json,reason) VALUES (?,?,?)", (row["rule_key"], json.dumps(row["effective_value"], ensure_ascii=False), row["reason"]))
        for row in data["source_conflicts"]:
            db.execute("INSERT INTO source_conflicts VALUES (?,?,?,?,?)", (row["conflict_id"], row["rule_key"], json.dumps(row["variants"], ensure_ascii=False), row["resolution_status"], row["resolution_note"]))
