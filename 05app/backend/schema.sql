PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_documents (
  source_document_id TEXT PRIMARY KEY, source_name TEXT NOT NULL,
  source_path TEXT NOT NULL, source_type TEXT NOT NULL, source_hash TEXT NOT NULL,
  parsed_at TEXT NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS source_conflicts (
  conflict_id TEXT PRIMARY KEY, rule_key TEXT NOT NULL, variants_json TEXT NOT NULL,
  resolution_status TEXT NOT NULL, resolution_note TEXT
);
CREATE TABLE IF NOT EXISTS product_overrides (
  rule_key TEXT PRIMARY KEY, effective_value_json TEXT NOT NULL,
  reason TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS levels (
  level_id INTEGER PRIMARY KEY, level_name TEXT NOT NULL,
  stage_positioning TEXT, active_in_demo INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS level_rules (
  level_rule_id TEXT PRIMARY KEY, level_id INTEGER NOT NULL REFERENCES levels(level_id),
  rule_key TEXT NOT NULL, raw_value TEXT NOT NULL, effective_value_json TEXT NOT NULL,
  value_type TEXT NOT NULL, rule_strength TEXT NOT NULL,
  source_document_id TEXT, source_section TEXT, note TEXT,
  UNIQUE(level_id, rule_key)
);
CREATE TABLE IF NOT EXISTS book_types (
  code TEXT PRIMARY KEY, display_name_zh TEXT UNIQUE NOT NULL,
  core_positioning TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS topics (
  topic_id TEXT PRIMARY KEY, level_id INTEGER NOT NULL REFERENCES levels(level_id),
  semester TEXT NOT NULL, unit_number INTEGER NOT NULL, topic_number INTEGER NOT NULL,
  unit_title TEXT NOT NULL DEFAULT '',
  theme TEXT NOT NULL, essential_question TEXT NOT NULL,
  grammar_text TEXT NOT NULL DEFAULT '',
  cross_curricular_text TEXT NOT NULL DEFAULT '',
  literature_text TEXT NOT NULL DEFAULT '',
  source_document_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
  active INTEGER NOT NULL, UNIQUE(level_id, topic_number),
  UNIQUE(level_id, semester, unit_number)
);
CREATE TABLE IF NOT EXISTS textbook_words (
  textbook_word_id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_id TEXT NOT NULL REFERENCES topics(topic_id), raw_entry TEXT NOT NULL,
  normalized_entry TEXT NOT NULL, entry_type TEXT NOT NULL, sequence_no INTEGER NOT NULL,
  source_document_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
  UNIQUE(topic_id, sequence_no)
);
CREATE TABLE IF NOT EXISTS textbook_structures (
  textbook_structure_id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_id TEXT NOT NULL REFERENCES topics(topic_id), raw_structure TEXT NOT NULL,
  normalized_pattern TEXT, sequence_no INTEGER NOT NULL,
  source_document_id TEXT NOT NULL REFERENCES source_documents(source_document_id),
  UNIQUE(topic_id, sequence_no)
);
CREATE TABLE IF NOT EXISTS textbook_examples (
  example_id INTEGER PRIMARY KEY AUTOINCREMENT, topic_id TEXT REFERENCES topics(topic_id),
  raw_sentence TEXT NOT NULL, source_section TEXT NOT NULL, sequence_no INTEGER NOT NULL,
  verification_status TEXT NOT NULL CHECK(verification_status IN ('verified','pending','rejected')),
  source_document_id TEXT NOT NULL REFERENCES source_documents(source_document_id), note TEXT
);
CREATE INDEX IF NOT EXISTS idx_textbook_words_entry ON textbook_words(normalized_entry);

-- Runtime foundation. Static rebuild never deletes from these tables.
CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(topic_id),
  working_title TEXT, status TEXT NOT NULL DEFAULT 'ACTIVE',
  selected_proposal_id TEXT, current_draft_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposal_batches (
  proposal_batch_id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(topic_id),
  target_book_type TEXT NOT NULL DEFAULT 'ALL', teacher_input_json TEXT NOT NULL DEFAULT '{}',
  original_proposal_count INTEGER NOT NULL CHECK(original_proposal_count >= 0),
  evaluation_json TEXT, selected_count INTEGER NOT NULL DEFAULT 0 CHECK(selected_count >= 0),
  discarded_count INTEGER NOT NULL DEFAULT 0 CHECK(discarded_count >= 0),
  selection_finalized_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (
  proposal_id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(project_id),
  proposal_batch_id TEXT NOT NULL REFERENCES proposal_batches(proposal_batch_id), proposal_index INTEGER,
  payload_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(proposal_batch_id, proposal_index)
);
CREATE TABLE IF NOT EXISTS pre_generation_plans (
  plan_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id),
  proposal_id TEXT NOT NULL REFERENCES proposals(proposal_id),
  page_count INTEGER NOT NULL CHECK(page_count IN (8,12)),
  generation_orientation TEXT NOT NULL CHECK(generation_orientation IN ('STORY','LANGUAGE','BALANCED')),
  teacher_instruction TEXT NOT NULL DEFAULT '', textbook_reference_json TEXT NOT NULL,
  review_candidates_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'DRAFT',
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS planned_vocabulary (
  planned_vocab_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES pre_generation_plans(plan_id),
  raw_form TEXT NOT NULL, normalized_form TEXT NOT NULL, lemma TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('CORE','EXTENSION','REVIEW')),
  source_lookup_status TEXT NOT NULL, manual_review_required INTEGER NOT NULL CHECK(manual_review_required IN (0,1)),
  teacher_confirmed INTEGER NOT NULL DEFAULT 0 CHECK(teacher_confirmed IN (0,1)),
  sequence_no INTEGER NOT NULL, UNIQUE(plan_id,normalized_form)
);
CREATE TABLE IF NOT EXISTS planned_patterns (
  planned_pattern_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES pre_generation_plans(plan_id),
  raw_pattern TEXT NOT NULL, normalized_pattern TEXT NOT NULL,
  source_relation TEXT NOT NULL, manual_review_required INTEGER NOT NULL CHECK(manual_review_required IN (0,1)),
  teacher_confirmed INTEGER NOT NULL DEFAULT 0 CHECK(teacher_confirmed IN (0,1)),
  sequence_no INTEGER NOT NULL, UNIQUE(plan_id,normalized_pattern)
);
CREATE TABLE IF NOT EXISTS full_text_candidates (
  candidate_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id),
  proposal_id TEXT NOT NULL REFERENCES proposals(proposal_id),
  plan_id TEXT NOT NULL REFERENCES pre_generation_plans(plan_id),
  candidate_batch_id TEXT NOT NULL, candidate_index INTEGER NOT NULL,
  title TEXT NOT NULL, page_count INTEGER NOT NULL, total_word_count INTEGER NOT NULL,
  generation_orientation TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'GENERATED',
  validation_json TEXT NOT NULL, content_hash TEXT NOT NULL,
  requires_fact_verification INTEGER NOT NULL DEFAULT 0 CHECK(requires_fact_verification IN (0,1)),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(candidate_batch_id,candidate_index)
);
CREATE TABLE IF NOT EXISTS full_text_candidate_pages (
  candidate_page_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES full_text_candidates(candidate_id),
  page_number INTEGER NOT NULL, page_text TEXT NOT NULL,
  UNIQUE(candidate_id,page_number)
);
CREATE TABLE IF NOT EXISTS draft_versions (
  draft_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id),
  proposal_id TEXT REFERENCES proposals(proposal_id), parent_draft_id TEXT REFERENCES draft_versions(draft_id),
  source_candidate_id TEXT REFERENCES full_text_candidates(candidate_id),
  version_number INTEGER NOT NULL, generation_orientation TEXT,
  page_count_target INTEGER CHECK(page_count_target IN (8,12)),
  status TEXT NOT NULL, content_hash TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS draft_pages (
  draft_page_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES draft_versions(draft_id),
  page_number INTEGER NOT NULL, page_text TEXT NOT NULL,
  created_at TEXT, updated_at TEXT, UNIQUE(draft_id,page_number)
);
CREATE TABLE IF NOT EXISTS validation_runs (
  validation_run_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES draft_versions(draft_id),
  validation_type TEXT NOT NULL, content_hash TEXT NOT NULL, overall_status TEXT NOT NULL,
  result_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS validation_issues (
  issue_id TEXT PRIMARY KEY,
  validation_run_id TEXT NOT NULL REFERENCES validation_runs(validation_run_id),
  issue_fingerprint TEXT NOT NULL, rule_key TEXT NOT NULL,
  severity TEXT NOT NULL, scope_json TEXT NOT NULL, message TEXT NOT NULL,
  resolution_status TEXT NOT NULL DEFAULT 'OPEN'
    CHECK(resolution_status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
  acknowledged_at TEXT, acknowledgement_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_validation_issues_run
  ON validation_issues(validation_run_id);
CREATE TABLE IF NOT EXISTS vocabulary_confirmations (
  confirmation_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES draft_versions(draft_id),
  plan_id TEXT NOT NULL REFERENCES pre_generation_plans(plan_id),
  confirmed_at TEXT NOT NULL, snapshot_json TEXT NOT NULL, content_hash TEXT NOT NULL, active INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_reviews (
  fact_review_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES draft_versions(draft_id),
  status TEXT NOT NULL, verification_note TEXT, verified_at TEXT, content_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS draft_vocab_observations (
  observation_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES draft_versions(draft_id),
  raw_form TEXT NOT NULL, normalized_form TEXT NOT NULL, lemma TEXT NOT NULL,
  token_count INTEGER NOT NULL, planned_role TEXT, detected_status TEXT NOT NULL,
  classification_state TEXT NOT NULL CHECK(classification_state IN ('PLANNED','KNOWN_UNPLANNED','NEEDS_REVIEW')),
  source_lookup_status TEXT NOT NULL, textbook_source_hit INTEGER NOT NULL,
  curriculum_source_hit INTEGER NOT NULL, historical_conflict_hit INTEGER NOT NULL,
  manual_review_required INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS draft_pattern_observations (
  pattern_observation_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES draft_versions(draft_id),
  target_pattern TEXT NOT NULL, normalized_pattern TEXT NOT NULL,
  matched_count INTEGER NOT NULL, matched_pages_json TEXT NOT NULL,
  manual_review_required INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rewrite_previews (
  rewrite_preview_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES draft_versions(draft_id),
  scope TEXT NOT NULL CHECK(scope IN ('FULL','PAGE')), target_page_number INTEGER,
  base_content_hash TEXT NOT NULL, teacher_instruction TEXT NOT NULL,
  output_json TEXT NOT NULL, validation_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('PREVIEW','ACCEPTED','CANCELLED')),
  created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS final_books (
  book_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id),
  draft_id TEXT NOT NULL REFERENCES draft_versions(draft_id), topic_id TEXT NOT NULL REFERENCES topics(topic_id),
  book_type_code TEXT NOT NULL REFERENCES book_types(code), title TEXT NOT NULL,
  book_number INTEGER,
  content_snapshot_json TEXT NOT NULL, finalized_at TEXT NOT NULL,
  is_current INTEGER NOT NULL, superseded_by_book_id TEXT REFERENCES final_books(book_id)
);
CREATE TABLE IF NOT EXISTS final_book_vocabulary (
  final_book_vocab_id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES final_books(book_id),
  raw_form TEXT NOT NULL, lemma TEXT NOT NULL, role TEXT NOT NULL, token_count INTEGER NOT NULL,
  UNIQUE(book_id,lemma,role)
);
CREATE TABLE IF NOT EXISTS recurrence_events (
  recurrence_event_id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES final_books(book_id),
  level_id INTEGER NOT NULL REFERENCES levels(level_id), lemma TEXT NOT NULL,
  token_count_in_book INTEGER NOT NULL, event_value INTEGER NOT NULL DEFAULT 1,
  is_active INTEGER NOT NULL, created_at TEXT NOT NULL, UNIQUE(book_id,lemma)
);

CREATE VIEW IF NOT EXISTS current_final_books AS SELECT * FROM final_books WHERE is_current=1;
CREATE VIEW IF NOT EXISTS current_final_vocabulary AS
  SELECT v.* FROM final_book_vocabulary v JOIN final_books b ON b.book_id=v.book_id WHERE b.is_current=1;
CREATE VIEW IF NOT EXISTS current_recurrence_counts AS
  SELECT level_id, lemma, COUNT(*) AS recurrence_count FROM recurrence_events
  WHERE is_active=1 GROUP BY level_id, lemma;
