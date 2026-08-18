"""Workflow-controlled Proposal generation; no Full Text or Final behavior."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .config import DATABASE_PATH, ModelSettings
from .context_service import ContextPreparationService
from .database import connect
from .model_adapter import ModelAdapter, ModelResult, OpenAICompatibleModelAdapter
from .proposal_prompt import LanguagePlanRecommendationAssembler, ProposalPromptAssembler
from .proposal_schema import (LANGUAGE_RECOMMENDATION_SCHEMA, PROPOSAL_OUTPUT_SCHEMA,
                              parse_model_json)
from .proposal_validation import ProposalValidator
from .services import ReferenceDataService


class ProposalWorkflow:
    def __init__(self, adapter: ModelAdapter | None = None, database_path: Path = DATABASE_PATH,
                 settings: ModelSettings | None = None):
        self.database_path = Path(database_path)
        self.settings = settings or ModelSettings.from_environment()
        self.adapter = adapter or OpenAICompatibleModelAdapter(self.settings)
        self.context_service = ContextPreparationService(self.database_path)
        self.reference = ReferenceDataService(self.database_path)
        self.prompt_assembler = ProposalPromptAssembler()
        self.language_prompt = LanguagePlanRecommendationAssembler()
        self.validator = ProposalValidator(self.reference)

    def generate_proposals(self, topic_id: str | int, count: int = 8,
                           teacher_input: dict | None = None,
                           target_book_type: str = "ALL") -> dict:
        if not 6 <= count <= 10:
            return self._failure("VALIDATION_FAILED", "Proposal count must be between 6 and 10", 0)
        teacher_input = teacher_input or {}
        try:
            context = self.context_service.prepare_proposal_context(topic_id, target_book_type)
            messages = self.prompt_assembler.assemble(context, teacher_input, count)
        except (KeyError, ValueError) as exc:
            return self._failure("VALIDATION_FAILED", str(exc), 0)
        model_config = {"model": self.settings.model_for("PROPOSAL"), "temperature": 0.8}
        attempts = 0
        last_error = None
        payload = None
        while attempts < 2:
            attempts += 1
            result = self.adapter.generate("PROPOSAL", messages, PROPOSAL_OUTPUT_SCHEMA, model_config)
            if not result.ok:
                return self._failure(result.error_code or "PROVIDER_ERROR",
                                     result.error_message or "Model provider failed", attempts)
            payload, parse_error = parse_model_json(result.text)
            if parse_error is None:
                break
            last_error = parse_error
            if attempts < 2:
                messages = messages + [{"role": "assistant", "content": result.text},
                                       {"role": "user", "content":
                                        "The previous output did not match the required JSON schema. Return only one valid JSON object with the proposals array; do not add commentary."}]
        if payload is None:
            return self._failure(last_error or "INVALID_SCHEMA", "Model output remained invalid after one retry", attempts)
        topic = context["authoritative_database_facts"]
        topic_for_validation = dict(topic["topic"])
        topic_for_validation["textbook_words"] = topic["textbook_words"]
        validation = self.validator.validate(payload, count, topic_for_validation, teacher_input)
        if not validation["valid"]:
            return {"ok": False, "error_code": "VALIDATION_FAILED",
                    "message": "Proposal quality validation failed", "attempts": attempts,
                    "validation": validation, "proposal_batch_id": None,
                    "proposals": []}
        try:
            saved = self._persist(topic_for_validation["topic_id"], validation,
                                  teacher_input, target_book_type)
        except (sqlite3.Error, ValueError) as exc:
            return self._failure("PERSISTENCE_ERROR", str(exc), attempts)
        return {"ok": True, "error_code": None, "message": "Proposals generated",
                "attempts": attempts, "proposal_batch_id": saved["proposal_batch_id"],
                "proposals": saved["proposals"], "validation": validation,
                "context_status": {"rag": context["rag_guidance"]["status"]}}

    def _persist(self, topic_id: str, validation: dict, teacher_input: dict,
                 target_book_type: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        batch_id = "proposal-batch-" + uuid4().hex
        saved = []
        with connect(self.database_path) as db:
            db.execute("""INSERT INTO proposal_batches
                (proposal_batch_id,topic_id,target_book_type,teacher_input_json,
                 original_proposal_count,evaluation_json,selected_count,discarded_count,
                 selection_finalized_at,created_at)
                VALUES (?,?,?,?,?,?,0,0,NULL,?)""",
                       (batch_id, topic_id, target_book_type,
                        json.dumps(teacher_input, ensure_ascii=False),
                        len(validation["proposals"]),
                        json.dumps(validation, ensure_ascii=False), now))
            for proposal in validation["proposals"]:
                proposal_id = "proposal-" + uuid4().hex
                payload = dict(proposal)
                payload["proposal_id"] = proposal_id
                payload["proposal_batch_id"] = batch_id
                payload["status"] = "GENERATED"
                db.execute("""INSERT INTO proposals
                    (proposal_id,project_id,proposal_batch_id,proposal_index,payload_json,status,created_at,updated_at)
                    VALUES (?,NULL,?,?,?,'GENERATED',?,?)""",
                    (proposal_id, batch_id, proposal["proposal_index"],
                     json.dumps(payload, ensure_ascii=False), now, now))
                saved.append(payload)
        return {"proposal_batch_id": batch_id, "proposals": saved}

    def create_manual_proposal(self, topic_id: str | int, manual_input: dict) -> dict:
        """Teacher-authored Proposal: no model call, established as a Project at once.

        Internally it still lives in a (single-proposal, immediately finalized)
        Proposal Batch so downstream stages see a normal SELECTED Proposal.
        """
        title = str(manual_input.get("title") or "").strip()
        storyline = str(manual_input.get("storyline") or "").strip()
        book_type = manual_input.get("book_type") or ""
        if not title or not storyline:
            return self._lifecycle_failure("MANUAL_FIELDS_REQUIRED",
                                           "title and storyline are required")
        if book_type not in {item["code"] for item in self.reference.get_book_types()}:
            return self._lifecycle_failure("INVALID_BOOK_TYPE",
                                           "book_type must be a concrete book type")
        topic = self.reference.get_topic_reference(topic_id)
        if topic is None:
            return self._lifecycle_failure("TOPIC_NOT_FOUND", "Topic not found")

        def clean_list(key: str) -> list[str]:
            values = [str(value).strip() for value in manual_input.get(key) or []]
            return list(dict.fromkeys(value for value in values if value))

        now = datetime.now(timezone.utc).isoformat()
        batch_id = "proposal-batch-" + uuid4().hex
        proposal_id = "proposal-" + uuid4().hex
        project_id = "project-" + uuid4().hex
        payload = {
            "proposal_id": proposal_id, "proposal_batch_id": batch_id,
            "proposal_index": 1, "title": title,
            "entry_point_cn": str(manual_input.get("entry_point_cn") or "").strip(),
            "storyline": storyline,
            "predicted_core_words": clean_list("predicted_core_words"),
            "predicted_core_patterns": clean_list("predicted_core_patterns"),
            "predicted_extension_words": clean_list("predicted_extension_words"),
            "book_type": book_type,
            "plot_structure": "", "potential_issues": "", "creative_highlight": "",
            "source": "MANUAL", "status": "SELECTED",
        }
        try:
            with connect(self.database_path) as db:
                db.execute("""INSERT INTO proposal_batches
                    (proposal_batch_id,topic_id,target_book_type,teacher_input_json,
                     original_proposal_count,evaluation_json,selected_count,discarded_count,
                     selection_finalized_at,created_at)
                    VALUES (?,?,?,?,1,'{}',1,0,?,?)""",
                           (batch_id, topic["topic_id"], book_type,
                            json.dumps({"source": "MANUAL"}, ensure_ascii=False), now, now))
                db.execute("""INSERT INTO projects
                    (project_id,topic_id,working_title,status,selected_proposal_id,
                     current_draft_id,created_at,updated_at)
                    VALUES (?,?,?,'ACTIVE',?,NULL,?,?)""",
                           (project_id, topic["topic_id"], title, proposal_id, now, now))
                db.execute("""INSERT INTO proposals
                    (proposal_id,project_id,proposal_batch_id,proposal_index,payload_json,
                     status,created_at,updated_at)
                    VALUES (?,?,?,1,?,'SELECTED',?,?)""",
                           (proposal_id, project_id, batch_id,
                            json.dumps(payload, ensure_ascii=False), now, now))
        except sqlite3.Error as exc:
            return self._lifecycle_failure("PERSISTENCE_ERROR", str(exc))
        return {"ok": True, "source": "MANUAL", "proposal_batch_id": batch_id,
                "proposal_id": proposal_id, "project_id": project_id,
                "projects": [{"project_id": project_id,
                              "selected_proposal_id": proposal_id, "status": "ACTIVE"}]}

    def recommend_language_for_proposal(self, proposal_id: str) -> dict:
        """AI language suggestions for an (typically teacher-authored) Proposal.

        Only fills the predicted_* suggestion fields on the Proposal payload; the
        story text is never rewritten, and nothing becomes READY without the
        teacher confirming a Pre-generation Plan. Any failure leaves the Proposal
        and its Project untouched so the teacher can retry or fill the plan by hand.
        """
        with connect(self.database_path) as db:
            row = db.execute("SELECT * FROM proposals WHERE proposal_id=?",
                             (proposal_id,)).fetchone()
            batch = row and db.execute(
                "SELECT topic_id FROM proposal_batches WHERE proposal_batch_id=?",
                (row["proposal_batch_id"],)).fetchone()
        if not row:
            return self._lifecycle_failure("PROPOSAL_NOT_FOUND", "Proposal not found")
        if not batch:
            return self._lifecycle_failure("TOPIC_NOT_FOUND", "Proposal has no Topic")
        payload = json.loads(row["payload_json"])
        book_type = payload.get("book_type")
        if book_type not in {item["code"] for item in self.reference.get_book_types()}:
            return self._lifecycle_failure("INVALID_BOOK_TYPE",
                                           "Proposal has no valid book type")
        try:
            context = self.context_service.prepare_proposal_context(
                batch["topic_id"], book_type)
        except (KeyError, ValueError) as exc:
            return self._lifecycle_failure("VALIDATION_FAILED", str(exc))
        messages = self.language_prompt.assemble(context, payload)
        model_config = {"model": self.settings.model_for("PROPOSAL"), "temperature": 0.5}
        attempts, last_error, recommendation = 0, None, None
        while attempts < 2:
            attempts += 1
            result = self.adapter.generate("PROPOSAL", messages,
                                           LANGUAGE_RECOMMENDATION_SCHEMA, model_config)
            if not result.ok:
                return {**self._lifecycle_failure(
                    result.error_code or "PROVIDER_ERROR",
                    result.error_message or "Model provider failed"),
                    "attempts": attempts}
            value, parse_error = parse_model_json(result.text)
            error = parse_error or _recommendation_payload_error(value)
            if error is None:
                recommendation = value
                break
            last_error = error
            if attempts < 2:
                messages = messages + [
                    {"role": "assistant", "content": result.text},
                    {"role": "user", "content":
                     "The previous output did not match the required JSON schema. Return only "
                     "one JSON object with predicted_core_words, predicted_extension_words, "
                     "and predicted_core_patterns; do not add commentary."}]
        if recommendation is None:
            return {**self._lifecycle_failure(
                "INVALID_SCHEMA",
                f"Model output remained invalid after one retry: {last_error}"),
                "attempts": attempts}
        limits = {"predicted_core_words": 5, "predicted_extension_words": 4,
                  "predicted_core_patterns": 2}
        cleaned = {}
        for key, limit in limits.items():
            values = [str(value).strip() for value in recommendation[key]]
            cleaned[key] = list(dict.fromkeys(
                value for value in values if value))[:limit]
        payload.update(cleaned)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with connect(self.database_path) as db:
                db.execute("UPDATE proposals SET payload_json=?,updated_at=? WHERE proposal_id=?",
                           (json.dumps(payload, ensure_ascii=False), now, proposal_id))
        except sqlite3.Error as exc:
            return self._lifecycle_failure("PERSISTENCE_ERROR", str(exc))
        return {"ok": True, "proposal_id": proposal_id, "attempts": attempts, **cleaned}

    def establish_projects_from_proposals(self, proposal_batch_id: str,
                                          proposal_ids: list[str]) -> dict:
        proposal_ids = list(dict.fromkeys(proposal_ids))
        if not proposal_ids:
            return self._lifecycle_failure("PROPOSALS_REQUIRED", "Select at least one Proposal")
        now = datetime.now(timezone.utc).isoformat()
        created = []
        try:
            with connect(self.database_path) as db:
                batch = db.execute(
                    "SELECT * FROM proposal_batches WHERE proposal_batch_id=?",
                    (proposal_batch_id,),
                ).fetchone()
                if not batch:
                    return self._lifecycle_failure("BATCH_NOT_FOUND", "Proposal Batch not found")
                if batch["selection_finalized_at"]:
                    return self._lifecycle_failure("BATCH_FINALIZED", "Proposal Batch selection is finalized")
                placeholders = ",".join("?" for _ in proposal_ids)
                rows = db.execute(
                    f"""SELECT * FROM proposals WHERE proposal_batch_id=?
                        AND proposal_id IN ({placeholders})""",
                    (proposal_batch_id, *proposal_ids),
                ).fetchall()
                if len(rows) != len(proposal_ids):
                    return self._lifecycle_failure(
                        "PROPOSAL_NOT_FOUND", "One or more Proposals do not belong to this Batch"
                    )
                if any(row["project_id"] is not None or row["status"] != "GENERATED" for row in rows):
                    return self._lifecycle_failure(
                        "PROPOSAL_ALREADY_ESTABLISHED", "A selected Proposal already has a Project"
                    )
                by_id = {row["proposal_id"]: row for row in rows}
                for proposal_id in proposal_ids:
                    row = by_id[proposal_id]
                    payload = json.loads(row["payload_json"])
                    project_id = "project-" + uuid4().hex
                    db.execute("""INSERT INTO projects
                        (project_id,topic_id,working_title,status,selected_proposal_id,
                         current_draft_id,created_at,updated_at)
                        VALUES (?,?,?,'ACTIVE',?,NULL,?,?)""",
                               (project_id, batch["topic_id"], payload.get("title"),
                                proposal_id, now, now))
                    db.execute("""UPDATE proposals SET project_id=?,status='SELECTED',updated_at=?
                                  WHERE proposal_id=?""", (project_id, now, proposal_id))
                    created.append({"project_id": project_id,
                                    "selected_proposal_id": proposal_id,
                                    "status": "ACTIVE"})
                selected_count = db.execute(
                    "SELECT COUNT(*) FROM proposals WHERE proposal_batch_id=? AND status='SELECTED'",
                    (proposal_batch_id,),
                ).fetchone()[0]
                db.execute(
                    "UPDATE proposal_batches SET selected_count=? WHERE proposal_batch_id=?",
                    (selected_count, proposal_batch_id),
                )
        except (sqlite3.Error, ValueError, json.JSONDecodeError) as exc:
            return self._lifecycle_failure("PERSISTENCE_ERROR", str(exc))
        return {"ok": True, "proposal_batch_id": proposal_batch_id,
                "established_count": len(created), "projects": created}

    def finalize_proposal_batch_selection(self, proposal_batch_id: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        try:
            with connect(self.database_path) as db:
                batch = db.execute(
                    "SELECT * FROM proposal_batches WHERE proposal_batch_id=?",
                    (proposal_batch_id,),
                ).fetchone()
                if not batch:
                    return self._lifecycle_failure("BATCH_NOT_FOUND", "Proposal Batch not found")
                if batch["selection_finalized_at"]:
                    return self._lifecycle_failure("BATCH_FINALIZED", "Proposal Batch selection is finalized")
                selected_count = db.execute(
                    "SELECT COUNT(*) FROM proposals WHERE proposal_batch_id=? AND project_id IS NOT NULL",
                    (proposal_batch_id,),
                ).fetchone()[0]
                discarded_count = db.execute(
                    "SELECT COUNT(*) FROM proposals WHERE proposal_batch_id=? AND project_id IS NULL",
                    (proposal_batch_id,),
                ).fetchone()[0]
                db.execute(
                    "DELETE FROM proposals WHERE proposal_batch_id=? AND project_id IS NULL",
                    (proposal_batch_id,),
                )
                db.execute("""UPDATE proposal_batches
                    SET selected_count=?,discarded_count=?,selection_finalized_at=?
                    WHERE proposal_batch_id=?""",
                           (selected_count, discarded_count, now, proposal_batch_id))
        except sqlite3.Error as exc:
            return self._lifecycle_failure("PERSISTENCE_ERROR", str(exc))
        return {"ok": True, "proposal_batch_id": proposal_batch_id,
                "selected_count": selected_count, "discarded_count": discarded_count,
                "selection_finalized_at": now}

    @staticmethod
    def _failure(code: str, message: str, attempts: int) -> dict:
        return {"ok": False, "error_code": code, "message": message, "attempts": attempts,
                "proposal_batch_id": None, "proposals": []}

    @staticmethod
    def _lifecycle_failure(code: str, message: str) -> dict:
        return {"ok": False, "error_code": code, "message": message}


def _recommendation_payload_error(value: dict | None) -> str | None:
    """Deterministic shape check for the language recommendation output."""
    if not isinstance(value, dict):
        return "Output must be a JSON object"
    for key in ("predicted_core_words", "predicted_extension_words",
                "predicted_core_patterns"):
        items = value.get(key)
        if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            return f"{key} must be a list of strings"
    if not [item for item in value["predicted_core_words"] if item.strip()]:
        return "predicted_core_words must not be empty"
    if not [item for item in value["predicted_core_patterns"] if item.strip()]:
        return "predicted_core_patterns must not be empty"
    return None


def generate_proposals(topic_id: str | int, count: int = 8, teacher_input: dict | None = None,
                       target_book_type: str = "ALL") -> dict:
    return ProposalWorkflow().generate_proposals(topic_id, count, teacher_input, target_book_type)


def establish_projects_from_proposals(proposal_batch_id: str,
                                      proposal_ids: list[str]) -> dict:
    return ProposalWorkflow().establish_projects_from_proposals(proposal_batch_id, proposal_ids)


def finalize_proposal_batch_selection(proposal_batch_id: str) -> dict:
    return ProposalWorkflow().finalize_proposal_batch_selection(proposal_batch_id)
