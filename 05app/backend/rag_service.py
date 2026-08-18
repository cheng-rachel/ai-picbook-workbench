"""Task-scoped local retrieval. No unrestricted search interface is exposed."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from .config import DOCS_DIR, RAG_INDEX_PATH, RAG_MANIFEST_PATH, RAG_PROCESSED_DIR
from .rag_builder import RAG_SOURCES, file_hash, tokenize

TASK_RULE_TYPES = {
    "PROPOSAL": {"DESIGN_PHILOSOPHY", "BOOK_TYPE_GUIDANCE", "TOPIC_GRADIENT", "PLOT_GUIDANCE",
                 "PRAGMATIC_NATURALNESS", "LEVEL_READING_GOAL", "CROSS_CURRICULAR"},
    "FULL_TEXT": {"PRAGMATIC_NATURALNESS", "LEVEL_READING_GOAL", "PATTERN_PRINCIPLE",
                  "VOCABULARY_PRINCIPLE", "RECURRENCE_PRINCIPLE", "FACTUAL_ACCURACY"},
    "VOCAB_CLASSIFICATION": {"VOCABULARY_PRINCIPLE"},
    "REVIEW_RECOMMENDATION": {"RECURRENCE_PRINCIPLE", "PRAGMATIC_NATURALNESS"},
}
ISSUE_RULE_TYPES = {
    "pattern": {"PATTERN_PRINCIPLE", "PRAGMATIC_NATURALNESS"},
    "mechanical_repetition": {"PATTERN_PRINCIPLE", "PRAGMATIC_NATURALNESS"},
    "culture": {"CROSS_CURRICULAR", "BOOK_TYPE_GUIDANCE"},
    "cross_curricular": {"CROSS_CURRICULAR", "BOOK_TYPE_GUIDANCE"},
    "vocabulary": {"VOCABULARY_PRINCIPLE", "PRAGMATIC_NATURALNESS"},
    "fact": {"FACTUAL_ACCURACY"},
    "plot": {"PLOT_GUIDANCE", "WRITING_METHOD"},
}


@dataclass(frozen=True)
class RagStatus:
    state: str
    message: str
    source_files: list[str]

    @property
    def available(self) -> bool:
        return self.state == "READY"

    def as_dict(self) -> dict:
        return {"state": self.state, "available": self.available,
                "message": self.message, "source_files": self.source_files}


class LocalRagService:
    def __init__(self, docs_dir: Path = DOCS_DIR, processed_dir: Path = RAG_PROCESSED_DIR,
                 index_path: Path = RAG_INDEX_PATH):
        self.docs_dir = Path(docs_dir)
        self.processed_dir = Path(processed_dir)
        self.index_path = Path(index_path)

    def status(self) -> RagStatus:
        manifest_path = self.processed_dir / "manifest.json"
        chunks_path = self.processed_dir / "teaching_guidance.jsonl"
        missing = [str(p) for p in (manifest_path, chunks_path, self.index_path) if not p.is_file()]
        if missing:
            return RagStatus("MISSING", "RAG index missing", missing)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
            chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line]
        except (OSError, json.JSONDecodeError) as exc:
            return RagStatus("INVALID", f"RAG index unreadable or invalid: {exc}", [self.index_path.name])
        if len(chunks) != manifest.get("chunk_count") or len(index.get("documents", [])) != len(chunks):
            return RagStatus("INVALID", "RAG index and processed chunks have inconsistent counts", [self.index_path.name])
        if index.get("source_hashes") != manifest.get("source_hashes"):
            return RagStatus("INVALID", "RAG index and manifest source hashes do not match", [self.index_path.name])
        stale = []
        for filename in RAG_SOURCES.values():
            path = self.docs_dir / filename
            if not path.is_file() or manifest.get("source_hashes", {}).get(filename) != file_hash(path):
                stale.append(filename)
        if stale:
            return RagStatus("STALE", "Source hash changed but RAG index was not rebuilt", stale)
        return RagStatus("READY", "RAG ready", [])

    def _load(self) -> tuple[list[dict], dict[str, dict[str, float]]]:
        chunks_path = self.processed_dir / "teaching_guidance.jsonl"
        chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line]
        index = json.loads(self.index_path.read_text(encoding="utf-8"))
        weights = {doc["chunk_id"]: doc["weights"] for doc in index["documents"]}
        return chunks, weights

    def _retrieve(self, task: str, level_id: int, rule_types: set[str], book_type: str = "ALL",
                  query_terms: Iterable[str] = (), top_k: int = 6) -> dict:
        status = self.status()
        if not status.available:
            return {"status": status.as_dict(), "results": []}
        chunks, weights = self._load()
        level_scope = f"LEVEL_{level_id}"
        filtered = [c for c in chunks
                    if c["rule_type"] in rule_types
                    and c["level_scope"] in ("ALL", level_scope)
                    and c["book_type_scope"] in ("ALL", book_type)
                    and ("ALL" in c["task_scope"] or task in c["task_scope"])]
        query = " ".join(query_terms) + " " + " ".join(rule_types)
        terms = tokenize(query)
        priority_boost = {"HIGH": 1.35, "NORMAL": 1.0, "LOW": 0.8}
        scored = []
        for chunk in filtered:
            score = sum(weights.get(chunk["chunk_id"], {}).get(term, 0) for term in terms)
            score = (score + 0.1) * priority_boost.get(chunk["priority"], 1.0)
            scored.append((score, chunk))
        # chunk_id makes source/semantic de-dup deterministic.
        seen, results = set(), []
        for score, chunk in sorted(scored, key=lambda item: (-item[0], item[1]["chunk_id"])):
            key = (chunk["source_document"], chunk["source_heading"], chunk["text"])
            if key in seen:
                continue
            seen.add(key)
            item = dict(chunk)
            item["score"] = round(score, 6)
            results.append(item)
            if len(results) >= top_k:
                break
        return {"status": status.as_dict(), "results": results}

    def retrieve_for_proposal(self, level_id: int, book_type: str) -> dict:
        return self._retrieve("PROPOSAL", level_id, TASK_RULE_TYPES["PROPOSAL"], book_type,
                              [book_type, "故事", "语用", "分级"])

    def retrieve_for_full_text(self, level_id: int, book_type: str) -> dict:
        return self._retrieve("FULL_TEXT", level_id, TASK_RULE_TYPES["FULL_TEXT"], book_type,
                              [book_type, "词汇", "句型", "复现", "事实"])

    def retrieve_for_vocab_classification(self, level_id: int) -> dict:
        return self._retrieve("VOCAB_CLASSIFICATION", level_id, TASK_RULE_TYPES["VOCAB_CLASSIFICATION"],
                              query_terms=["词汇", "收录", "分类"])

    def retrieve_for_review_recommendation(self, level_id: int) -> dict:
        return self._retrieve("REVIEW_RECOMMENDATION", level_id, TASK_RULE_TYPES["REVIEW_RECOMMENDATION"],
                              query_terms=["复现", "自然语境"])

    def retrieve_for_rewrite(self, level_id: int, issue_types: list[str], book_type: str = "ALL") -> dict:
        rule_types = set().union(*(ISSUE_RULE_TYPES.get(issue, set()) for issue in issue_types))
        if not rule_types:
            rule_types = {"PRAGMATIC_NATURALNESS"}
        return self._retrieve("REWRITE", level_id, rule_types, book_type, issue_types)
