"""M4 backend workflow: selection, language plan, candidates, Draft and rewrites."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .config import DATABASE_PATH, ModelSettings
from .context_service import ContextPreparationService
from .database import connect
from .draft_validation import (ALLOWED_PAGE_COUNTS, ORIENTATIONS, DraftValidator,
                               content_hash, normalize_phrase)
from .full_text_prompt import FullTextPromptAssembler, RewritePromptAssembler
from .full_text_schema import (FULL_TEXT_OUTPUT_SCHEMA, parse_json_object_diagnostic)
from .model_adapter import ModelAdapter, OpenAICompatibleModelAdapter
from .repository import normalize_lemma, textbook_lookup_forms
from .services import HistoricalVocabularyService, ReferenceDataService


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FullTextWorkflow:
    def __init__(self, adapter: ModelAdapter | None = None,
                 database_path: Path = DATABASE_PATH,
                 settings: ModelSettings | None = None):
        self.database_path = Path(database_path)
        self.settings = settings or ModelSettings.from_environment()
        self.adapter = adapter or OpenAICompatibleModelAdapter(self.settings)
        self.context = ContextPreparationService(self.database_path)
        self.reference = ReferenceDataService(self.database_path)
        self.history = HistoricalVocabularyService(self.database_path)
        self.validator = DraftValidator(self.reference, self.history)
        self.full_text_prompt = FullTextPromptAssembler()
        self.rewrite_prompt = RewritePromptAssembler()

    def select_proposal(self, project_id: str, proposal_id: str) -> dict:
        """Compatibility read: Project establishment now owns Proposal selection."""
        with connect(self.database_path) as db:
            project = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
            proposal = db.execute("SELECT * FROM proposals WHERE proposal_id=? AND project_id=?",
                                  (proposal_id, project_id)).fetchone()
            if not project:
                return self._failure("PROJECT_NOT_FOUND", "Project not found")
            if not proposal:
                return self._failure("PROPOSAL_NOT_FOUND", "Proposal does not belong to Project")
            if project["selected_proposal_id"] != proposal_id or proposal["status"] != "SELECTED":
                return self._failure(
                    "USE_BATCH_ESTABLISHMENT",
                    "Use establish_projects_from_proposals() to create an independent Project",
                )
        return {"ok": True, "project_id": project_id, "selected_proposal_id": proposal_id,
                "status": "SELECTED"}

    def prepare_generation_plan(self, project_id: str, page_count: int,
                                generation_orientation: str = "BALANCED",
                                teacher_instruction: str = "",
                                planned_core_words: list[str] | None = None,
                                planned_extension_words: list[str] | None = None,
                                planned_review_words: list[str] | None = None,
                                planned_core_patterns: list[str] | None = None,
                                non_teaching_context_words: list[str] | None = None) -> dict:
        if non_teaching_context_words:
            return self._failure(
                "NON_TEACHING_NOT_PLAN_ROLE",
                "NON_TEACHING_CONTEXT is confirmed at vocabulary review and is not a READY Language Plan role",
            )
        if page_count not in ALLOWED_PAGE_COUNTS:
            return self._failure("INVALID_PAGE_COUNT", "page_count must be 8 or 12")
        if generation_orientation not in ORIENTATIONS:
            return self._failure("INVALID_ORIENTATION",
                                 "generation_orientation must be STORY, LANGUAGE, or BALANCED")
        with connect(self.database_path) as db:
            project = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
            if not project:
                return self._failure("PROJECT_NOT_FOUND", "Project not found")
            if not project["selected_proposal_id"]:
                return self._failure("PROPOSAL_NOT_SELECTED", "Teacher must select a Proposal first")
            row = db.execute("SELECT payload_json,status FROM proposals WHERE proposal_id=?",
                             (project["selected_proposal_id"],)).fetchone()
        if not row or row["status"] != "SELECTED":
            return self._failure("PROPOSAL_NOT_SELECTED", "Selected Proposal state is inconsistent")
        proposal = json.loads(row["payload_json"])
        topic = self.reference.get_topic_reference(project["topic_id"])
        if topic is None:
            return self._failure("TOPIC_NOT_FOUND", "Project Topic not found")

        textbook_patterns = {normalize_phrase(pattern): pattern for pattern in topic["textbook_structures"]}
        promoted_patterns: list[str] = []
        raw_core = list(proposal.get("predicted_core_words", [])) if planned_core_words is None \
            else list(planned_core_words)
        filtered_core = []
        for raw in raw_core:
            normalized = normalize_phrase(raw)
            if normalized in textbook_patterns:
                promoted_patterns.append(textbook_patterns[normalized])
            else:
                filtered_core.append(raw)
        raw_patterns = list(proposal.get("predicted_core_patterns", [])) \
            if planned_core_patterns is None else list(planned_core_patterns)
        raw_patterns.extend(promoted_patterns)
        raw_extension = list(proposal.get("predicted_extension_words", [])) \
            if planned_extension_words is None else list(planned_extension_words)
        raw_review = list(planned_review_words or [])
        review_candidates = self.history.get_review_candidates(topic["level_id"], topic["topic_id"])

        vocab_items = []
        seen_vocab = set()
        for role, values in (("CORE", filtered_core), ("EXTENSION", raw_extension),
                             ("REVIEW", raw_review)):
            for raw in values:
                normalized = normalize_phrase(str(raw))
                if not normalized or normalized in seen_vocab:
                    continue
                seen_vocab.add(normalized)
                source, lemma = self._lookup_vocabulary(str(raw), topic)
                vocab_items.append({"raw_form": str(raw), "normalized_form": normalized,
                                    "lemma": lemma, "role": role,
                                    "source_lookup_status": source,
                                    "manual_review_required": source == "UNRESOLVED",
                                    "teacher_confirmed": False})

        pattern_items = []
        seen_patterns = set()
        for raw in raw_patterns:
            normalized = normalize_phrase(str(raw))
            if not normalized or normalized in seen_patterns:
                continue
            seen_patterns.add(normalized)
            relation = "TEXTBOOK" if normalized in textbook_patterns else "UNRESOLVED"
            pattern_items.append({"raw_pattern": str(raw), "normalized_pattern": normalized,
                                  "source_relation": relation,
                                  "manual_review_required": relation == "UNRESOLVED"})

        textbook_reference = {
            "topic": {key: topic[key] for key in
                      ("topic_id", "unit_title", "theme", "essential_question",
                       "grammar_text", "cross_curricular_text", "literature_text")},
            "textbook_words": topic["textbook_words"],
            "textbook_structures": topic["textbook_structures"],
            "textbook_examples": topic["textbook_examples"],
        }
        plan_id = "plan-" + uuid4().hex
        now = _now()
        with connect(self.database_path) as db:
            db.execute("UPDATE pre_generation_plans SET active=0,updated_at=? WHERE project_id=? AND active=1",
                       (now, project_id))
            db.execute("""INSERT INTO pre_generation_plans
                (plan_id,project_id,proposal_id,page_count,generation_orientation,teacher_instruction,
                 textbook_reference_json,review_candidates_json,status,active,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,'DRAFT',1,?,?)""",
                       (plan_id, project_id, project["selected_proposal_id"], page_count,
                        generation_orientation, teacher_instruction,
                        json.dumps(textbook_reference, ensure_ascii=False),
                        json.dumps(review_candidates, ensure_ascii=False), now, now))
            for index, item in enumerate(vocab_items, 1):
                db.execute("""INSERT INTO planned_vocabulary
                    (planned_vocab_id,plan_id,raw_form,normalized_form,lemma,role,source_lookup_status,
                     manual_review_required,teacher_confirmed,sequence_no) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                           ("planned-vocab-" + uuid4().hex, plan_id, item["raw_form"],
                            item["normalized_form"], item["lemma"], item["role"],
                            item["source_lookup_status"], int(item["manual_review_required"]), 0, index))
            for index, item in enumerate(pattern_items, 1):
                db.execute("""INSERT INTO planned_patterns
                    (planned_pattern_id,plan_id,raw_pattern,normalized_pattern,source_relation,
                     manual_review_required,sequence_no) VALUES (?,?,?,?,?,?,?)""",
                           ("planned-pattern-" + uuid4().hex, plan_id, item["raw_pattern"],
                            item["normalized_pattern"], item["source_relation"],
                            int(item["manual_review_required"]), index))
        return {"ok": True, **self._load_plan(plan_id), "selected_proposal": proposal}

    def confirm_generation_plan(self, plan_id: str) -> dict:
        now = _now()
        with connect(self.database_path) as db:
            plan = db.execute(
                "SELECT status,active FROM pre_generation_plans WHERE plan_id=?", (plan_id,)
            ).fetchone()
            if not plan:
                return self._failure("PLAN_NOT_FOUND", "Pre-generation Plan not found")
            if not plan["active"]:
                return self._failure("PLAN_NOT_ACTIVE", "Pre-generation Plan is not active")
            if plan["status"] not in {"DRAFT", "READY"}:
                return self._failure("INVALID_PLAN_STATUS", "Pre-generation Plan cannot be confirmed")
            db.execute(
                "UPDATE planned_vocabulary SET teacher_confirmed=1 WHERE plan_id=?", (plan_id,)
            )
            db.execute(
                "UPDATE planned_patterns SET teacher_confirmed=1 WHERE plan_id=?", (plan_id,)
            )
            db.execute(
                "UPDATE pre_generation_plans SET status='READY',updated_at=? WHERE plan_id=?",
                (now, plan_id),
            )
            project_id = db.execute(
                "SELECT project_id FROM pre_generation_plans WHERE plan_id=?", (plan_id,)
            ).fetchone()[0]
            current = db.execute(
                "SELECT current_draft_id FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()
            db.execute("""UPDATE vocabulary_confirmations SET active=0
                          WHERE draft_id=? AND active=1 AND (plan_id IS NULL OR plan_id<>?)""",
                       (current["current_draft_id"], plan_id)) if current and current["current_draft_id"] else None
        if current and current["current_draft_id"]:
            draft = self._load_draft_by_id(current["current_draft_id"])
            with connect(self.database_path) as db:
                topic_id = db.execute("SELECT topic_id FROM projects WHERE project_id=?",
                                      (project_id,)).fetchone()[0]
            validation = self.validator.validate(
                draft["pages"], self._load_plan(plan_id),
                self.reference.get_topic_reference(topic_id),
            )
            self._persist_validation(draft["draft_id"], validation, "plan_change")
        return {"ok": True, **self._load_plan(plan_id)}

    def revise_generation_plan_from_vocabulary(self, draft_id: str,
                                               selections: list[dict]) -> dict:
        """Create or extend a DRAFT Plan revision; never mutate a READY Plan.

        The first promotion derives a DRAFT revision from the active READY Plan.
        Until the teacher confirms that revision, further promotions extend it
        (each call still produces a fresh DRAFT row, keeping revisions immutable).
        """
        draft = self._load_draft_by_id(draft_id)
        if draft is None:
            return self._failure("DRAFT_NOT_FOUND", "Draft not found")
        allowed_roles = {"CORE", "EXTENSION", "REVIEW"}
        with connect(self.database_path) as db:
            base = db.execute("""SELECT * FROM pre_generation_plans
                WHERE project_id=? AND active=1
                ORDER BY updated_at DESC LIMIT 1""", (draft["project_id"],)).fetchone()
            ever_confirmed = db.execute(
                """SELECT COUNT(*) FROM pre_generation_plans
                   WHERE project_id=? AND status='READY'""",
                (draft["project_id"],)).fetchone()[0]
            observations = {row["normalized_form"]: dict(row) for row in db.execute(
                "SELECT * FROM draft_vocab_observations WHERE draft_id=?", (draft_id,))}
        # A DRAFT active plan is only acceptable as a pending revision, i.e. the
        # project must have had a teacher-confirmed READY Plan at some point.
        if not base or (base["status"] != "READY" and not ever_confirmed):
            return self._failure("PLAN_NOT_READY", "An active READY Plan is required")
        promoted = {"CORE": [], "EXTENSION": [], "REVIEW": []}
        for item in selections:
            normalized = normalize_phrase(str(item.get("normalized_form", "")))
            role = item.get("role")
            observation = observations.get(normalized)
            if not observation or observation["classification_state"] == "PLANNED":
                return self._failure("VOCABULARY_OBSERVATION_MISMATCH",
                                     f"{normalized} is not a promotable current observation")
            if role not in allowed_roles:
                return self._failure("INVALID_VOCABULARY_ROLE",
                                     "Promotion role must be CORE, EXTENSION, or REVIEW")
            promoted[role].append(observation["raw_form"])
        old = self._load_plan(base["plan_id"])
        role_values = lambda role: [item["raw_form"] for item in old["planned_vocabulary"]
                                    if item["role"] == role] + promoted[role]
        return self.prepare_generation_plan(
            draft["project_id"], old["page_count"], old["generation_orientation"],
            old["teacher_instruction"], role_values("CORE"), role_values("EXTENSION"),
            role_values("REVIEW"),
            [item["raw_pattern"] for item in old["planned_core_patterns"]],
        )

    def generate_full_text_candidates(self, plan_id: str, candidate_count: int = 3) -> dict:
        if candidate_count not in {2, 3}:
            return self._failure("INVALID_CANDIDATE_COUNT", "candidate_count must be 2 or 3")
        try:
            plan = self._load_plan(plan_id)
        except KeyError:
            return self._failure("PLAN_NOT_FOUND", "Pre-generation Plan not found")
        if not plan["active"] or plan["status"] != "READY":
            return self._failure("PLAN_NOT_READY", "Pre-generation Plan is not active and ready")
        with connect(self.database_path) as db:
            project = db.execute("SELECT * FROM projects WHERE project_id=?", (plan["project_id"],)).fetchone()
            proposal_row = db.execute("SELECT payload_json,status FROM proposals WHERE proposal_id=?",
                                      (plan["proposal_id"],)).fetchone()
        if not project or project["selected_proposal_id"] != plan["proposal_id"] or \
                not proposal_row or proposal_row["status"] != "SELECTED":
            return self._failure("PROPOSAL_NOT_SELECTED", "Plan Proposal is not the active teacher selection")
        proposal = json.loads(proposal_row["payload_json"])
        context = self.context.prepare_full_text_context(project["topic_id"], proposal["book_type"])
        messages = self.full_text_prompt.assemble(context, proposal, plan, candidate_count)
        payload, attempts, failure = self._call_structured(
            "FULL_TEXT", messages, FULL_TEXT_OUTPUT_SCHEMA,
            {"model": self.settings.model_for("FULL_TEXT"), "temperature": 0.7},
            lambda value: self._candidate_payload_error(value, candidate_count, plan))
        if failure:
            return {**failure, "attempts": attempts}

        topic = self.reference.get_topic_reference(project["topic_id"])
        batch_id = "full-text-batch-" + uuid4().hex
        now = _now()
        saved = []
        with connect(self.database_path) as db:
            for raw_candidate in payload["candidates"]:
                candidate_id = "candidate-" + uuid4().hex
                pages = sorted(raw_candidate["pages"], key=lambda item: item["page_number"])
                validation = self.validator.validate(pages, plan, topic)
                candidate = {
                    "candidate_id": candidate_id, "candidate_batch_id": batch_id,
                    "candidate_index": raw_candidate["candidate_index"],
                    "title": raw_candidate["title"], "page_count": len(pages), "pages": pages,
                    "total_word_count": validation["metrics"]["total_word_count"],
                    "generation_orientation": plan["generation_orientation"],
                    "requires_fact_verification": raw_candidate["requires_fact_verification"],
                    "status": "GENERATED", "validation": validation,
                }
                db.execute("""INSERT INTO full_text_candidates
                    (candidate_id,project_id,proposal_id,plan_id,candidate_batch_id,candidate_index,title,
                     page_count,total_word_count,generation_orientation,status,validation_json,content_hash,
                     requires_fact_verification,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,'GENERATED',?,?,?,?,?)""",
                           (candidate_id, plan["project_id"], plan["proposal_id"], plan_id, batch_id,
                            candidate["candidate_index"], candidate["title"], candidate["page_count"],
                            candidate["total_word_count"], candidate["generation_orientation"],
                            json.dumps(validation, ensure_ascii=False), validation["content_hash"],
                            int(candidate["requires_fact_verification"]), now, now))
                for page in pages:
                    db.execute("INSERT INTO full_text_candidate_pages VALUES (?,?,?,?)",
                               ("candidate-page-" + uuid4().hex, candidate_id,
                                page["page_number"], page["text"]))
                saved.append(candidate)
        return {"ok": True, "attempts": attempts, "project_id": plan["project_id"],
                "full_text_candidate_batch_id": batch_id, "candidate_count": len(saved),
                "candidates": saved, "context_status": {"rag": context["rag_guidance"]["status"]}}

    def select_candidate_as_draft(self, candidate_id: str) -> dict:
        with connect(self.database_path) as db:
            candidate = db.execute("SELECT * FROM full_text_candidates WHERE candidate_id=?",
                                   (candidate_id,)).fetchone()
            if not candidate:
                return self._failure("CANDIDATE_NOT_FOUND", "Full-text Candidate not found")
            project = db.execute("SELECT * FROM projects WHERE project_id=?",
                                 (candidate["project_id"],)).fetchone()
            if project["selected_proposal_id"] != candidate["proposal_id"]:
                return self._failure("PROPOSAL_NOT_SELECTED", "Candidate Proposal is no longer selected")
            if project["current_draft_id"]:
                return self._failure("CURRENT_DRAFT_EXISTS", "Project already has a Current Draft")
            pages = [dict(row) for row in db.execute(
                "SELECT page_number,page_text AS text FROM full_text_candidate_pages WHERE candidate_id=? ORDER BY page_number",
                (candidate_id,))]
        plan = self._load_plan(candidate["plan_id"])
        topic = self.reference.get_topic_reference(project["topic_id"])
        validation = self.validator.validate(pages, plan, topic)
        draft_id = "draft-" + uuid4().hex
        now = _now()
        with connect(self.database_path) as db:
            db.execute("""INSERT INTO draft_versions
                (draft_id,project_id,proposal_id,parent_draft_id,source_candidate_id,version_number,
                 generation_orientation,page_count_target,status,content_hash,created_at,updated_at)
                VALUES (?,?,?,NULL,?,1,?,?,'DRAFT',?,?,?)""",
                       (draft_id, candidate["project_id"], candidate["proposal_id"], candidate_id,
                        candidate["generation_orientation"], plan["page_count"],
                        validation["content_hash"], now, now))
            for page in pages:
                db.execute("""INSERT INTO draft_pages
                    (draft_page_id,draft_id,page_number,page_text,created_at,updated_at)
                    VALUES (?,?,?,?,?,?)""",
                           ("draft-page-" + uuid4().hex, draft_id, page["page_number"],
                            page["text"], now, now))
            db.execute("UPDATE full_text_candidates SET status='SELECTED',updated_at=? WHERE candidate_id=?",
                       (now, candidate_id))
            db.execute("UPDATE projects SET current_draft_id=?,working_title=?,updated_at=? WHERE project_id=?",
                       (draft_id, candidate["title"], now, candidate["project_id"]))
            fact_status = "REQUIRED" if candidate["requires_fact_verification"] else "NOT_REQUIRED"
            db.execute("""INSERT INTO fact_reviews
                (fact_review_id,draft_id,status,verification_note,verified_at,content_hash)
                VALUES (?,?,?,NULL,NULL,?)""",
                       ("fact-review-" + uuid4().hex, draft_id, fact_status,
                        validation["content_hash"]))
        self._persist_validation(draft_id, validation, "full")
        return {"ok": True, "candidate_id": candidate_id, "draft": self.get_current_draft(
            candidate["project_id"])}

    def autosave_draft(self, draft_id: str, pages: list[dict],
                       requires_fact_verification: bool | None = None) -> dict:
        with connect(self.database_path) as db:
            draft = db.execute("SELECT * FROM draft_versions WHERE draft_id=?", (draft_id,)).fetchone()
            if not draft:
                return self._failure("DRAFT_NOT_FOUND", "Draft not found")
            project = db.execute("SELECT * FROM projects WHERE project_id=?", (draft["project_id"],)).fetchone()
            if project["status"] == "FINAL":
                return self._failure("PROJECT_FINAL",
                                     "Final Project text is frozen; withdraw the Final first")
            if project["current_draft_id"] != draft_id:
                return self._failure("NOT_CURRENT_DRAFT", "Only Current Draft can be autosaved")
            ready = db.execute("""SELECT plan_id FROM pre_generation_plans
                WHERE project_id=? AND active=1 AND status='READY'
                ORDER BY updated_at DESC LIMIT 1""", (draft["project_id"],)).fetchone()
        if not ready:
            return self._failure("PLAN_NOT_READY", "Current Project has no active READY Plan")
        plan = self._load_plan(ready["plan_id"])
        topic = self.reference.get_topic_reference(project["topic_id"])
        validation = self.validator.validate(pages, plan, topic)
        now = _now()
        with connect(self.database_path) as db:
            db.execute("DELETE FROM draft_pages WHERE draft_id=?", (draft_id,))
            for page in sorted(pages, key=lambda item: item["page_number"]):
                db.execute("""INSERT INTO draft_pages
                    (draft_page_id,draft_id,page_number,page_text,created_at,updated_at)
                    VALUES (?,?,?,?,?,?)""",
                           ("draft-page-" + uuid4().hex, draft_id, page["page_number"],
                            page.get("text", ""), now, now))
            db.execute("UPDATE draft_versions SET content_hash=?,status='DRAFT',updated_at=? WHERE draft_id=?",
                       (validation["content_hash"], now, draft_id))
            db.execute("UPDATE projects SET updated_at=? WHERE project_id=?", (now, draft["project_id"]))
            db.execute("UPDATE vocabulary_confirmations SET active=0 WHERE draft_id=? AND active=1",
                       (draft_id,))
            fact = db.execute("SELECT * FROM fact_reviews WHERE draft_id=?", (draft_id,)).fetchone()
            if fact:
                requested = requires_fact_verification
                if requested is True or fact["status"] == "VERIFIED_BY_USER":
                    db.execute("""UPDATE fact_reviews SET status='REQUIRED',verification_note=NULL,
                                  verified_at=NULL,content_hash=? WHERE draft_id=?""",
                               (validation["content_hash"], draft_id))
                else:
                    db.execute("UPDATE fact_reviews SET content_hash=? WHERE draft_id=?",
                               (validation["content_hash"], draft_id))
        self._persist_validation(draft_id, validation, "incremental")
        return {"ok": True, "draft_id": draft_id, "validation": validation,
                "draft": self.get_current_draft(draft["project_id"])}

    def create_rewrite_preview(self, draft_id: str, scope: str,
                               teacher_instruction: str,
                               page_number: int | None = None,
                               issue_types: list[str] | None = None) -> dict:
        scope = scope.upper()
        if scope not in {"FULL", "PAGE"} or (scope == "PAGE" and not page_number):
            return self._failure("INVALID_REWRITE_SCOPE", "Use FULL or PAGE with page_number")
        draft = self._load_draft_by_id(draft_id)
        if draft is None:
            return self._failure("DRAFT_NOT_FOUND", "Draft not found")
        with connect(self.database_path) as db:
            candidate = db.execute("SELECT plan_id FROM full_text_candidates WHERE candidate_id=?",
                                   (draft["source_candidate_id"],)).fetchone()
            proposal_row = db.execute("SELECT payload_json FROM proposals WHERE proposal_id=?",
                                      (draft["proposal_id"],)).fetchone()
            project = db.execute("SELECT topic_id FROM projects WHERE project_id=?",
                                 (draft["project_id"],)).fetchone()
            latest = db.execute("SELECT result_json FROM validation_runs WHERE draft_id=? ORDER BY created_at DESC LIMIT 1",
                                (draft_id,)).fetchone()
        plan = self._load_plan(candidate["plan_id"])
        proposal = json.loads(proposal_row["payload_json"])
        issue_types = issue_types or self._issue_types(json.loads(latest["result_json"]) if latest else {})
        rag = self.context.prepare_rewrite_guidance(project["topic_id"], proposal["book_type"], issue_types)
        messages, schema = self.rewrite_prompt.assemble(
            draft, proposal, plan, json.loads(latest["result_json"]) if latest else {}, rag,
            teacher_instruction, scope, page_number, locked_content=[])
        payload, attempts, failure = self._call_structured(
            "REWRITE", messages, schema,
            {"model": self.settings.model_for("REWRITE"), "temperature": 0.6},
            lambda value: self._rewrite_payload_error(value, scope, page_number))
        if failure:
            return {**failure, "attempts": attempts}
        preview_pages = payload["pages"] if scope == "FULL" else [
            {"page_number": payload["page_number"], "text": payload["text"]}]
        if scope == "PAGE":
            combined = [dict(page) for page in draft["pages"]]
            for page in combined:
                if page["page_number"] == page_number:
                    page["text"] = payload["text"]
            validation_pages = combined
        else:
            validation_pages = preview_pages
        topic = self.reference.get_topic_reference(project["topic_id"])
        validation = self.validator.validate(validation_pages, plan, topic)
        preview_id = "rewrite-preview-" + uuid4().hex
        with connect(self.database_path) as db:
            db.execute("""INSERT INTO rewrite_previews
                (rewrite_preview_id,draft_id,scope,target_page_number,base_content_hash,teacher_instruction,
                 output_json,validation_json,status,created_at,resolved_at)
                VALUES (?,?,?,?,?,?,?,?,'PREVIEW',?,NULL)""",
                       (preview_id, draft_id, scope, page_number, draft["content_hash"],
                        teacher_instruction, json.dumps(payload, ensure_ascii=False),
                        json.dumps(validation, ensure_ascii=False), _now()))
        return {"ok": True, "attempts": attempts, "rewrite_preview_id": preview_id,
                "status": "PREVIEW", "scope": scope, "output": payload,
                "validation": validation, "draft_overwritten": False,
                "context_status": {"rag": rag["status"]}}

    def accept_rewrite_preview(self, rewrite_preview_id: str) -> dict:
        with connect(self.database_path) as db:
            preview = db.execute("SELECT * FROM rewrite_previews WHERE rewrite_preview_id=?",
                                 (rewrite_preview_id,)).fetchone()
            if not preview:
                return self._failure("PREVIEW_NOT_FOUND", "Rewrite Preview not found")
            if preview["status"] != "PREVIEW":
                return self._failure("PREVIEW_RESOLVED", "Rewrite Preview is already resolved")
            draft = self._load_draft_by_id(preview["draft_id"], db)
        if draft["content_hash"] != preview["base_content_hash"]:
            return self._failure("STALE_PREVIEW", "Current Draft changed after Preview generation")
        output = json.loads(preview["output_json"])
        if preview["scope"] == "FULL":
            pages = output["pages"]
        else:
            pages = [dict(page) for page in draft["pages"]]
            for page in pages:
                if page["page_number"] == preview["target_page_number"]:
                    page["text"] = output["text"]
        saved = self.autosave_draft(preview["draft_id"], pages,
                                    output.get("requires_fact_verification"))
        if not saved["ok"]:
            return saved
        with connect(self.database_path) as db:
            db.execute("UPDATE rewrite_previews SET status='ACCEPTED',resolved_at=? WHERE rewrite_preview_id=?",
                       (_now(), rewrite_preview_id))
            if preview["scope"] == "FULL" and output.get("title"):
                db.execute("UPDATE projects SET working_title=?,updated_at=? WHERE current_draft_id=?",
                           (output["title"], _now(), preview["draft_id"]))
        return {"ok": True, "rewrite_preview_id": rewrite_preview_id,
                "status": "ACCEPTED", "draft": saved["draft"],
                "validation": saved["validation"]}

    def cancel_rewrite_preview(self, rewrite_preview_id: str) -> dict:
        with connect(self.database_path) as db:
            preview = db.execute("SELECT status,draft_id FROM rewrite_previews WHERE rewrite_preview_id=?",
                                 (rewrite_preview_id,)).fetchone()
            if not preview:
                return self._failure("PREVIEW_NOT_FOUND", "Rewrite Preview not found")
            if preview["status"] != "PREVIEW":
                return self._failure("PREVIEW_RESOLVED", "Rewrite Preview is already resolved")
            before = db.execute("SELECT content_hash FROM draft_versions WHERE draft_id=?",
                                (preview["draft_id"],)).fetchone()[0]
            db.execute("UPDATE rewrite_previews SET status='CANCELLED',resolved_at=? WHERE rewrite_preview_id=?",
                       (_now(), rewrite_preview_id))
            after = db.execute("SELECT content_hash FROM draft_versions WHERE draft_id=?",
                               (preview["draft_id"],)).fetchone()[0]
        return {"ok": True, "rewrite_preview_id": rewrite_preview_id,
                "status": "CANCELLED", "draft_unchanged": before == after}

    def confirm_vocabulary(self, draft_id: str, snapshot: dict) -> dict:
        draft = self._load_draft_by_id(draft_id)
        if draft is None:
            return self._failure("DRAFT_NOT_FOUND", "Draft not found")
        entries = snapshot.get("entries") if isinstance(snapshot, dict) else None
        if not isinstance(entries, list):
            return self._failure("INVALID_VOCABULARY_SNAPSHOT",
                                 "snapshot.entries must be a list")
        required = {"raw_form", "normalized_form", "lemma", "source_status",
                    "classification_state", "confirmed_role", "teacher_confirmed"}
        roles = {"CORE", "EXTENSION", "REVIEW", "NON_TEACHING_CONTEXT"}
        source_statuses = {"TEXTBOOK", "TEXTBOOK_SCOPE", "UNRESOLVED"}
        with connect(self.database_path) as db:
            latest = db.execute(
                """SELECT validation_run_id,content_hash FROM validation_runs
                   WHERE draft_id=? ORDER BY created_at DESC,validation_run_id DESC LIMIT 1""",
                (draft_id,),
            ).fetchone()
            observations = [dict(row) for row in db.execute(
                """SELECT raw_form,normalized_form,lemma,source_lookup_status,classification_state
                   FROM draft_vocab_observations WHERE draft_id=?""", (draft_id,)
            )]
            ready_plan = db.execute("""SELECT plan_id FROM pre_generation_plans
                WHERE project_id=? AND active=1 AND status='READY'
                ORDER BY updated_at DESC LIMIT 1""", (draft["project_id"],)).fetchone()
        if not latest or latest["content_hash"] != draft["content_hash"]:
            return self._failure("VALIDATION_REQUIRED",
                                 "Current Draft must have a current Validation Run")
        if not ready_plan:
            return self._failure("PLAN_NOT_READY", "Current Project has no active READY Plan")
        expected = {(item["normalized_form"], item["lemma"]): item for item in observations}
        canonical_entries = []
        supplied_keys = set()
        for index, item in enumerate(entries):
            if not isinstance(item, dict) or not required.issubset(item):
                return self._failure("INVALID_VOCABULARY_SNAPSHOT",
                                     f"Vocabulary entry {index + 1} is missing required fields")
            if item["confirmed_role"] not in roles or item["source_status"] not in source_statuses or \
                    not isinstance(item["teacher_confirmed"], bool):
                return self._failure("INVALID_VOCABULARY_SNAPSHOT",
                                     f"Vocabulary entry {index + 1} has an invalid role, source, or confirmation")
            key = (item["normalized_form"], item["lemma"])
            source = expected.get(key)
            if source is None or item["raw_form"] != source["raw_form"]:
                return self._failure("VOCABULARY_OBSERVATION_MISMATCH",
                                     f"Vocabulary entry {index + 1} does not match current Validation")
            if item["source_status"] != source["source_lookup_status"]:
                return self._failure("SOURCE_STATUS_IMMUTABLE",
                                     "Teacher role confirmation cannot change source_status")
            if item["classification_state"] != source["classification_state"]:
                return self._failure("CLASSIFICATION_STATE_IMMUTABLE",
                                     "Teacher confirmation cannot change classification_state")
            if source["classification_state"] != "NEEDS_REVIEW":
                return self._failure("VOCABULARY_CONFIRMATION_NOT_REQUIRED",
                                     "Only NEEDS_REVIEW observations require vocabulary confirmation")
            if item["confirmed_role"] in {"CORE", "EXTENSION", "REVIEW"}:
                return self._failure(
                    "PLAN_REVISION_REQUIRED",
                    "Teaching-role promotion must create and confirm a DRAFT Plan revision",
                )
            supplied_keys.add(key)
            canonical_entries.append({field: item[field] for field in required})
        required_keys = {key for key, item in expected.items()
                         if item["classification_state"] == "NEEDS_REVIEW"}
        missing = sorted("|".join(key) for key in required_keys - supplied_keys)
        unconfirmed = sorted(item["normalized_form"] for item in canonical_entries
                             if not item["teacher_confirmed"])
        readiness = {"ready_for_final": not (missing or unconfirmed),
                     "missing_entries": missing, "unconfirmed_entries": unconfirmed,
                     "unclassified_entries": []}
        structured_snapshot = {"plan_id": ready_plan["plan_id"],
                               "content_hash": draft["content_hash"],
                               "entries": canonical_entries, "readiness": readiness}
        confirmation_id = "vocab-confirmation-" + uuid4().hex
        with connect(self.database_path) as db:
            db.execute("UPDATE vocabulary_confirmations SET active=0 WHERE draft_id=?", (draft_id,))
            db.execute("""INSERT INTO vocabulary_confirmations
                (confirmation_id,draft_id,plan_id,confirmed_at,snapshot_json,content_hash,active)
                VALUES (?,?,?,?,?,?,1)""",
                       (confirmation_id, draft_id, ready_plan["plan_id"], _now(),
                        json.dumps(structured_snapshot, ensure_ascii=False),
                        draft["content_hash"]))
        if readiness["ready_for_final"]:
            confirmations = {(item["normalized_form"], item["lemma"]): item
                             for item in canonical_entries}
            with connect(self.database_path) as db:
                topic_id = db.execute("SELECT topic_id FROM projects WHERE project_id=?",
                                      (draft["project_id"],)).fetchone()[0]
            validation = self.validator.validate(
                draft["pages"], self._load_plan(ready_plan["plan_id"]),
                self.reference.get_topic_reference(topic_id), confirmations,
            )
            self._persist_validation(draft_id, validation, "vocabulary_confirmation")
        return {"ok": True, "confirmation_id": confirmation_id, "active": True,
                "content_hash": draft["content_hash"], "snapshot": structured_snapshot,
                **readiness}

    def acknowledge_validation_issue(self, issue_id: str,
                                      acknowledgement_note: str | None = None) -> dict:
        with connect(self.database_path) as db:
            issue = db.execute("SELECT * FROM validation_issues WHERE issue_id=?", (issue_id,)).fetchone()
            if not issue:
                return self._failure("ISSUE_NOT_FOUND", "Validation issue not found")
            if issue["severity"] != "WARNING":
                return self._failure("ISSUE_NOT_ACKNOWLEDGEABLE", "Only Warning issues may be acknowledged")
            if issue["resolution_status"] == "RESOLVED":
                return self._failure("ISSUE_RESOLVED", "Resolved issue cannot be acknowledged")
            acknowledged_at = issue["acknowledged_at"] or _now()
            db.execute("""UPDATE validation_issues
                SET resolution_status='ACKNOWLEDGED',acknowledged_at=?,acknowledgement_note=?
                WHERE issue_id=?""", (acknowledged_at, acknowledgement_note, issue_id))
        return {"ok": True, "issue_id": issue_id, "resolution_status": "ACKNOWLEDGED",
                "acknowledged_at": acknowledged_at,
                "acknowledgement_note": acknowledgement_note}

    def resolve_validation_issue(self, issue_id: str) -> dict:
        with connect(self.database_path) as db:
            issue = db.execute("SELECT issue_id FROM validation_issues WHERE issue_id=?", (issue_id,)).fetchone()
            if not issue:
                return self._failure("ISSUE_NOT_FOUND", "Validation issue not found")
            db.execute("""UPDATE validation_issues SET resolution_status='RESOLVED'
                          WHERE issue_id=?""", (issue_id,))
        return {"ok": True, "issue_id": issue_id, "resolution_status": "RESOLVED"}

    def update_fact_review(self, draft_id: str, status: str,
                           verification_note: str | None = None) -> dict:
        if status not in {"NOT_REQUIRED", "REQUIRED", "VERIFIED_BY_USER"}:
            return self._failure("INVALID_FACT_STATUS", "Invalid fact verification status")
        if status == "VERIFIED_BY_USER" and not (verification_note or "").strip():
            return self._failure("VERIFICATION_NOTE_REQUIRED", "Verification note is required")
        draft = self._load_draft_by_id(draft_id)
        if draft is None:
            return self._failure("DRAFT_NOT_FOUND", "Draft not found")
        verified_at = _now() if status == "VERIFIED_BY_USER" else None
        with connect(self.database_path) as db:
            db.execute("""UPDATE fact_reviews SET status=?,verification_note=?,verified_at=?,content_hash=?
                          WHERE draft_id=?""",
                       (status, verification_note, verified_at, draft["content_hash"], draft_id))
        return {"ok": True, "draft_id": draft_id, "status": status,
                "verification_note": verification_note, "content_hash": draft["content_hash"]}

    def get_current_draft(self, project_id: str) -> dict | None:
        with connect(self.database_path) as db:
            project = db.execute("SELECT current_draft_id,working_title FROM projects WHERE project_id=?",
                                 (project_id,)).fetchone()
            if not project or not project["current_draft_id"]:
                return None
            draft = self._load_draft_by_id(project["current_draft_id"], db)
            latest = db.execute("SELECT validation_run_id,result_json FROM validation_runs WHERE draft_id=? ORDER BY created_at DESC,validation_run_id DESC LIMIT 1",
                                (project["current_draft_id"],)).fetchone()
            fact = db.execute("SELECT status,verification_note,content_hash FROM fact_reviews WHERE draft_id=?",
                              (project["current_draft_id"],)).fetchone()
            confirmation = db.execute("""SELECT confirmation_id,plan_id,content_hash,active FROM vocabulary_confirmations
                WHERE draft_id=? ORDER BY confirmed_at DESC LIMIT 1""",
                                      (project["current_draft_id"],)).fetchone()
            issues = [dict(row) for row in db.execute(
                """SELECT issue_id,issue_fingerprint,rule_key,severity,scope_json,message,
                          resolution_status,acknowledged_at,acknowledgement_note
                   FROM validation_issues WHERE validation_run_id=? ORDER BY rowid""",
                (latest["validation_run_id"],),
            )] if latest else []
        draft["title"] = project["working_title"]
        draft["validation"] = json.loads(latest["result_json"]) if latest else None
        draft["validation_issues"] = issues
        for issue in draft["validation_issues"]:
            issue["scope"] = json.loads(issue.pop("scope_json"))
        draft["fact_review"] = dict(fact) if fact else None
        draft["vocabulary_confirmation"] = dict(confirmation) if confirmation else None
        return draft

    def _lookup_vocabulary(self, raw: str, topic: dict) -> tuple[str, str]:
        normalized = normalize_phrase(raw)
        lemma = normalize_lemma(normalized)
        current_unit = {normalize_phrase(form)
                        for form in textbook_lookup_forms(topic["textbook_words"])}
        if normalized in current_unit:
            return "TEXTBOOK", lemma
        scope_hits = self.reference.lookup_textbook_entry(raw)
        return ("TEXTBOOK_SCOPE" if scope_hits else "UNRESOLVED"), lemma

    def _load_plan(self, plan_id: str) -> dict:
        with connect(self.database_path) as db:
            row = db.execute("SELECT * FROM pre_generation_plans WHERE plan_id=?", (plan_id,)).fetchone()
            if not row:
                raise KeyError(plan_id)
            plan = dict(row)
            plan["active"] = bool(plan["active"])
            plan["teacher_instruction"] = plan["teacher_instruction"] or ""
            plan["textbook_reference"] = json.loads(plan.pop("textbook_reference_json"))
            plan["review_candidates"] = json.loads(plan.pop("review_candidates_json"))
            plan["planned_vocabulary"] = [dict(item) for item in db.execute(
                """SELECT raw_form,normalized_form,lemma,role,source_lookup_status,
                   manual_review_required,teacher_confirmed FROM planned_vocabulary
                   WHERE plan_id=? ORDER BY sequence_no""", (plan_id,))]
            for item in plan["planned_vocabulary"]:
                item["manual_review_required"] = bool(item["manual_review_required"])
                item["teacher_confirmed"] = bool(item["teacher_confirmed"])
            plan["planned_core_words"] = [item for item in plan["planned_vocabulary"] if item["role"] == "CORE"]
            plan["planned_extension_words"] = [item for item in plan["planned_vocabulary"] if item["role"] == "EXTENSION"]
            plan["planned_review_words"] = [item for item in plan["planned_vocabulary"] if item["role"] == "REVIEW"]
            plan["planned_core_patterns"] = [dict(item) for item in db.execute(
                """SELECT raw_pattern,normalized_pattern,source_relation,manual_review_required,
                          teacher_confirmed
                   FROM planned_patterns WHERE plan_id=? ORDER BY sequence_no""", (plan_id,))]
            for item in plan["planned_core_patterns"]:
                item["manual_review_required"] = bool(item["manual_review_required"])
                item["teacher_confirmed"] = bool(item["teacher_confirmed"])
            return plan

    def _load_draft_by_id(self, draft_id: str, db: sqlite3.Connection | None = None) -> dict | None:
        owns = db is None
        connection = db or connect(self.database_path)
        try:
            row = connection.execute("SELECT * FROM draft_versions WHERE draft_id=?", (draft_id,)).fetchone()
            if not row:
                return None
            draft = dict(row)
            draft["pages"] = [dict(page) for page in connection.execute(
                "SELECT page_number,page_text AS text FROM draft_pages WHERE draft_id=? ORDER BY page_number",
                (draft_id,))]
            return draft
        finally:
            if owns:
                connection.close()

    def _persist_validation(self, draft_id: str, validation: dict, validation_type: str) -> str:
        now = _now()
        validation_run_id = "validation-" + uuid4().hex
        with connect(self.database_path) as db:
            db.execute("""INSERT INTO validation_runs
                (validation_run_id,draft_id,validation_type,content_hash,overall_status,result_json,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                       (validation_run_id, draft_id, validation_type,
                        validation["content_hash"], validation["overall_status"],
                        json.dumps(validation, ensure_ascii=False), now))
            for issue in validation.get("issues", []):
                fingerprint_payload = {
                    "rule_key": issue["rule_key"], "severity": issue["severity"],
                    "scope": issue.get("scope", {}), "message": issue["message"],
                }
                fingerprint = sha256(json.dumps(
                    fingerprint_payload, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")).hexdigest()
                db.execute("""INSERT INTO validation_issues
                    (issue_id,validation_run_id,issue_fingerprint,rule_key,severity,scope_json,
                     message,resolution_status,acknowledged_at,acknowledgement_note)
                    VALUES (?,?,?,?,?,?,?,'OPEN',NULL,NULL)""",
                           ("issue-" + uuid4().hex, validation_run_id, fingerprint,
                            issue["rule_key"], issue["severity"],
                            json.dumps(issue.get("scope", {}), ensure_ascii=False),
                            issue["message"]))
            db.execute("DELETE FROM draft_vocab_observations WHERE draft_id=?", (draft_id,))
            for item in validation["vocabulary_observations"]:
                db.execute("""INSERT INTO draft_vocab_observations
                    (observation_id,draft_id,raw_form,normalized_form,lemma,token_count,
                     planned_role,detected_status,classification_state,source_lookup_status,
                     textbook_source_hit,curriculum_source_hit,historical_conflict_hit,
                     manual_review_required) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           ("observation-" + uuid4().hex, draft_id, item["raw_form"],
                            item["normalized_form"], item["lemma"], item["token_count"],
                            item["planned_role"], item["detected_status"],
                            item["classification_state"],
                            item["source_lookup_status"], int(item["textbook_source_hit"]),
                            int(item["curriculum_source_hit"]), int(item["historical_conflict_hit"]),
                            int(item["manual_review_required"])))
            db.execute("DELETE FROM draft_pattern_observations WHERE draft_id=?", (draft_id,))
            for item in validation["pattern_observations"]:
                db.execute("""INSERT INTO draft_pattern_observations VALUES
                    (?,?,?,?,?,?,?)""",
                           ("pattern-observation-" + uuid4().hex, draft_id,
                            item["target_pattern"], item["normalized_pattern"],
                            item["matched_count"], json.dumps(item["matched_pages"]),
                            int(item["manual_review_required"])))
        return validation_run_id

    def _call_structured(self, task_type: str, messages: list[dict], schema: dict,
                         model_config: dict, semantic_error) -> tuple[dict | None, int, dict | None]:
        attempts = 0
        diagnostics = []
        last_error = {"code": "INVALID_SCHEMA", "message": "Schema validation failed",
                      "failed_field_path": "$"}
        while attempts < 2:
            attempts += 1
            result = self.adapter.generate(task_type, messages, schema, model_config)
            if not result.ok:
                failure = self._failure(result.error_code or "PROVIDER_ERROR",
                                        result.error_message or "Model provider failed")
                failure["schema_failure_attempts"] = diagnostics
                return None, attempts, failure
            payload, parse_error = parse_json_object_diagnostic(result.text)
            schema_error = semantic_error(payload) if payload is not None else None
            last_error = parse_error or schema_error
            if last_error is None:
                return payload, attempts, None
            diagnostics.append({
                "provider_model": (result.provider_metadata or {}).get("model")
                                  or model_config.get("model"),
                "attempt_number": attempts,
                "raw_response_content": result.text,
                "parse_error": parse_error,
                "schema_validation_error": schema_error,
                "failed_field_path": last_error.get("failed_field_path", "$"),
            })
            if attempts < 2:
                messages = messages + [{"role": "assistant", "content": result.text},
                                       {"role": "user", "content":
                                        "The previous output did not match the required schema or requested count. Return only one corrected JSON object."}]
        failure = self._failure("INVALID_SCHEMA", "Model output remained invalid after one retry")
        failure["schema_failure_attempts"] = diagnostics
        return None, attempts, failure

    @staticmethod
    def _candidate_payload_error(payload: dict, expected_count: int, plan: dict) -> dict | None:
        def invalid(path: str, message: str) -> dict:
            return {"code": "INVALID_SCHEMA", "message": message,
                    "failed_field_path": path}

        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if not isinstance(candidates, list):
            return invalid("$.candidates", "candidates must be an array")
        if len(candidates) != expected_count:
            return invalid("$.candidates", f"Expected {expected_count} candidates; received {len(candidates)}")
        expected_indices = list(range(1, expected_count + 1))
        actual_indices = [item.get("candidate_index") if isinstance(item, dict) else None
                          for item in candidates]
        if actual_indices != expected_indices:
            return invalid("$.candidates[*].candidate_index",
                           f"Expected candidate indices {expected_indices}; received {actual_indices}")
        for candidate_offset, item in enumerate(candidates):
            base = f"$.candidates[{candidate_offset}]"
            if not isinstance(item, dict):
                return invalid(base, "Candidate must be an object")
            if not isinstance(item.get("title"), str):
                return invalid(f"{base}.title", "title must be a string")
            if not isinstance(item.get("page_count"), int):
                return invalid(f"{base}.page_count", "page_count must be an integer")
            if not isinstance(item.get("pages"), list):
                return invalid(f"{base}.pages", "pages must be an array")
            if not isinstance(item.get("requires_fact_verification"), bool):
                return invalid(f"{base}.requires_fact_verification",
                               "requires_fact_verification must be a boolean")
            for page_offset, page in enumerate(item["pages"]):
                page_base = f"{base}.pages[{page_offset}]"
                if not isinstance(page, dict):
                    return invalid(page_base, "Page must be an object")
                if not isinstance(page.get("page_number"), int):
                    return invalid(f"{page_base}.page_number", "page_number must be an integer")
                if not isinstance(page.get("text"), str):
                    return invalid(f"{page_base}.text", "text must be a string")
        return None

    @staticmethod
    def _rewrite_payload_error(payload: dict, scope: str, page_number: int | None) -> dict | None:
        def invalid(path: str, message: str) -> dict:
            return {"code": "INVALID_SCHEMA", "message": message,
                    "failed_field_path": path}

        if not isinstance(payload, dict) or not isinstance(payload.get("requires_fact_verification"), bool):
            return invalid("$.requires_fact_verification",
                           "requires_fact_verification must be a boolean")
        if scope == "FULL":
            if not isinstance(payload.get("title"), str) or not isinstance(payload.get("pages"), list):
                return invalid("$", "Full rewrite requires string title and pages array")
            for index, page in enumerate(payload["pages"]):
                if not isinstance(page, dict) or not isinstance(page.get("page_number"), int) or \
                        not isinstance(page.get("text"), str):
                    return invalid(f"$.pages[{index}]", "Page requires integer page_number and string text")
            return None
        if payload.get("page_number") != page_number:
            return invalid("$.page_number", f"page_number must equal {page_number}")
        if not isinstance(payload.get("text"), str):
            return invalid("$.text", "text must be a string")
        return None

    @staticmethod
    def _issue_types(validation: dict) -> list[str]:
        mapping = {"PATTERN": "pattern", "VOCAB": "vocabulary", "HISTORY": "vocabulary",
                   "FACT": "fact", "PAGE": "plot", "WORDCOUNT": "plot"}
        found = []
        for issue in validation.get("issues", []):
            rule = issue.get("rule_key", "")
            for key, value in mapping.items():
                if key in rule and value not in found:
                    found.append(value)
        return found or ["plot"]

    @staticmethod
    def _failure(code: str, message: str) -> dict:
        return {"ok": False, "error_code": code, "message": message}
