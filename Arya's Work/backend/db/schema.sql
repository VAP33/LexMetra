-- LMPC Compliance Platform — PostgreSQL schema
--
-- MVP persistence layer.
--
-- Core entities:
--   products
--   inspections
--   inspection_facts
--
-- The schema intentionally stays relational and small. Rich OCR/CV evidence
-- that is not yet normalized is stored as JSON in inspection_facts.evidence_json.
-- Legal decisions remain represented by explicit status/rule/version fields.
--
-- Production additions such as users, roles and a complete audit trail should
-- be added with the authentication/reviewer workflow rather than prematurely
-- coupling them to the inspection MVP.

-- Users / role-based access control.
--
-- Roles:
--   inspector - can create inspections, view own history
--   reviewer  - can additionally resolve UNCERTAIN findings / mark reviewed
--   admin     - can additionally manage users
CREATE TABLE IF NOT EXISTS users (
    user_id             SERIAL PRIMARY KEY,
    username            TEXT NOT NULL UNIQUE,
    full_name           TEXT,
    hashed_password     TEXT NOT NULL,
    role                TEXT NOT NULL DEFAULT 'inspector',
    -- 'inspector' | 'reviewer' | 'admin'
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    product_id          TEXT PRIMARY KEY,
    category            TEXT,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inspections (
    inspection_id       TEXT PRIMARY KEY,
    product_id          TEXT REFERENCES products(product_id),
    sale_type           TEXT NOT NULL,
    product_category    TEXT NOT NULL,

    net_quantity_value  NUMERIC,
    net_quantity_unit   TEXT,
    mrp                 NUMERIC,

    overall_status      TEXT NOT NULL,
    -- PASS | FAIL | UNCERTAIN | EXEMPT

    exempt_reason       TEXT,

    image_filename      TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    reviewed            BOOLEAN NOT NULL DEFAULT FALSE,
    reviewer_note       TEXT,

    -- Aggregate review state for the frontend/review queue.
    -- Kept separate from individual fact review_required flags.
    review_required     BOOLEAN NOT NULL DEFAULT FALSE,

    -- Canonical, evidence-backed declarations used by the current UI/history.
    declarations_json   JSONB
);

CREATE INDEX IF NOT EXISTS idx_inspections_product
    ON inspections(product_id);

CREATE INDEX IF NOT EXISTS idx_inspections_status
    ON inspections(overall_status);

CREATE INDEX IF NOT EXISTS idx_inspections_created
    ON inspections(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_inspections_review
    ON inspections(reviewed)
    WHERE reviewed = FALSE;

CREATE INDEX IF NOT EXISTS idx_inspections_needs_review
    ON inspections(review_required)
    WHERE review_required = TRUE;


CREATE TABLE IF NOT EXISTS inspection_facts (
    id                  SERIAL PRIMARY KEY,

    inspection_id       TEXT NOT NULL
                        REFERENCES inspections(inspection_id)
                        ON DELETE CASCADE,

    field               TEXT NOT NULL,

    extracted_value     TEXT,

    status              TEXT NOT NULL,
    -- PASS | FAIL | UNCERTAIN | EXEMPT

    confidence          NUMERIC,

    rule_id             TEXT,
    rule_version        TEXT,

    reason              TEXT,

    review_required     BOOLEAN NOT NULL DEFAULT FALSE,

    -- Structured evidence such as:
    -- [
    --   {
    --     "image_id": "...",
    --     "bbox": [x, y, w, h],
    --     "measurement_mode": "VERIFIED",
    --     "evidence_status": "OBSERVED"
    --   }
    -- ]
    --
    -- JSON is used here because evidence structure will evolve during the MVP
    -- without requiring a migration for every new CV/OCR metadata field.
    evidence_json       JSONB
);

CREATE INDEX IF NOT EXISTS idx_facts_inspection
    ON inspection_facts(inspection_id);

CREATE INDEX IF NOT EXISTS idx_facts_field
    ON inspection_facts(field);

CREATE INDEX IF NOT EXISTS idx_facts_status
    ON inspection_facts(status);

CREATE INDEX IF NOT EXISTS idx_facts_rule
    ON inspection_facts(rule_id);

CREATE INDEX IF NOT EXISTS idx_facts_review
    ON inspection_facts(review_required)
    WHERE review_required = TRUE;


-- ---------------------------------------------------------------------------
-- inspection_findings
--
-- The legal verdicts themselves, one row per evaluated rule.
--
-- WHY THIS TABLE WAS ADDED. It did not exist. `save_inspection()` persisted
-- products, inspections and inspection_facts only, so every RuleFinding — the
-- object that carries the requirement evaluated, the rule version applied, the
-- evidence it rested on, and what evidence was MISSING — was discarded the
-- moment the request ended. `get_inspection_detail()` returned no findings, and
-- because `report.py` falls back to facts when findings are absent
-- (`rows_source = findings if findings else facts`), the generated PDF silently
-- rendered facts in their place. The fallback meant the omission produced a
-- plausible-looking document instead of an error, which is why it survived.
--
-- A finding must remain traceable to its evidence and to the rule version that
-- produced it after persistence and reload, not merely while it is in memory.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS inspection_findings (
    id                      SERIAL PRIMARY KEY,

    inspection_id           TEXT NOT NULL
                            REFERENCES inspections(inspection_id)
                            ON DELETE CASCADE,

    rule_id                 TEXT NOT NULL,
    rule_version            TEXT,

    status                  TEXT NOT NULL,
    -- PASS | FAIL | UNCERTAIN | EXEMPT

    requirement_id          TEXT,
    requirement_description TEXT,

    reason                  TEXT,

    confidence              NUMERIC,
    review_required         BOOLEAN NOT NULL DEFAULT FALSE,

    verification_status     TEXT,

    -- Same structure as inspection_facts.evidence_json: a list of
    -- EvidenceReference objects, each naming a source image_id and the region
    -- within it. See schema.UNATTRIBUTED_IMAGE_ID for how a missing source
    -- image is recorded so it cannot be mistaken for a real filename.
    evidence_json           JSONB,

    -- Evidence the rule REQUIRED versus what was actually absent. Kept
    -- separate from `reason` because "no evidence was observed" and "evidence
    -- was observed and contradicts the declaration" are different legal
    -- positions and must stay machine-distinguishable after reload.
    required_evidence_json  JSONB,
    missing_evidence_json    JSONB
);

CREATE INDEX IF NOT EXISTS idx_findings_inspection
    ON inspection_findings(inspection_id);

CREATE INDEX IF NOT EXISTS idx_findings_rule
    ON inspection_findings(rule_id);

CREATE INDEX IF NOT EXISTS idx_findings_status
    ON inspection_findings(status);

CREATE INDEX IF NOT EXISTS idx_findings_review
    ON inspection_findings(review_required)
    WHERE review_required = TRUE;


-- ---------------------------------------------------------------------------
-- Lightweight data-integrity constraints
-- ---------------------------------------------------------------------------
--
-- These constraints prevent obvious impossible database states. They do not
-- encode Legal Metrology policy, which belongs in rules.json + rule_engine.py.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'inspections_status_check'
    ) THEN
        ALTER TABLE inspections
        ADD CONSTRAINT inspections_status_check
        CHECK (overall_status IN ('PASS', 'FAIL', 'UNCERTAIN', 'EXEMPT'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'inspection_facts_status_check'
    ) THEN
        ALTER TABLE inspection_facts
        ADD CONSTRAINT inspection_facts_status_check
        CHECK (status IN ('PASS', 'FAIL', 'UNCERTAIN', 'EXEMPT'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'inspections_mrp_nonnegative'
    ) THEN
        ALTER TABLE inspections
        ADD CONSTRAINT inspections_mrp_nonnegative
        CHECK (mrp IS NULL OR mrp >= 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'inspections_quantity_nonnegative'
    ) THEN
        ALTER TABLE inspections
        ADD CONSTRAINT inspections_quantity_nonnegative
        CHECK (
            net_quantity_value IS NULL
            OR net_quantity_value > 0
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'inspection_facts_confidence_range'
    ) THEN
        ALTER TABLE inspection_facts
        ADD CONSTRAINT inspection_facts_confidence_range
        CHECK (
            confidence IS NULL
            OR (confidence >= 0 AND confidence <= 1)
        );
    END IF;

    -- Evidence retention: full on-disk path of the stored original image,
    -- separate from the display-only image_filename.
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'inspections' AND column_name = 'image_path'
    ) THEN
        ALTER TABLE inspections ADD COLUMN image_path TEXT;
    END IF;

    -- Attribution: which authenticated inspector performed the scan.
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'inspections' AND column_name = 'created_by'
    ) THEN
        ALTER TABLE inspections ADD COLUMN created_by TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'inspections' AND column_name = 'reviewed_by'
    ) THEN
        ALTER TABLE inspections ADD COLUMN reviewed_by TEXT;
    END IF;
END $$;

-- Audit trail: append-only log of security/workflow-relevant actions.
-- Kept separate from inspection_facts (legal evidence) so audit logging can
-- never be mistaken for a legal finding.
CREATE TABLE IF NOT EXISTS audit_log (
    id                  SERIAL PRIMARY KEY,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_username      TEXT,
    action              TEXT NOT NULL,
    -- e.g. 'login', 'scan_created', 'inspection_reviewed', 'user_created'
    resource_type       TEXT,
    resource_id         TEXT,
    detail              TEXT,
    ip_address          TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_occurred
    ON audit_log(occurred_at DESC);

-- Database-level enforcement: application code must never be able to rewrite
-- or delete audit history, even if a future endpoint is accidentally added.
CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only; UPDATE/DELETE is prohibited';
END;
$$;

DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log;
CREATE TRIGGER audit_log_append_only
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_log_mutation();

-- ---------------------------------------------------------------------------
-- Multi-surface inspection sessions
-- ---------------------------------------------------------------------------
-- One InspectionSession accumulates any number of SurfaceObservation
-- captures (front/back/rotated views, etc.) before a single deterministic
-- legal evaluation is run against the UNION of all evidence gathered.
CREATE TABLE IF NOT EXISTS inspection_sessions (
    session_id              TEXT PRIMARY KEY,
    product_id               TEXT NOT NULL,
    sale_type                 TEXT NOT NULL DEFAULT 'retail',
    product_category          TEXT NOT NULL DEFAULT 'food',

    net_quantity_value         NUMERIC,
    net_quantity_unit          TEXT,
    mrp                        NUMERIC,
    pdp_area_cm2               NUMERIC,
    is_export_only             BOOLEAN NOT NULL DEFAULT FALSE,
    retail_bundle_count        INTEGER,
    is_imported_hint           BOOLEAN,

    status                     TEXT NOT NULL DEFAULT 'OPEN',
    -- OPEN | FINALIZED | ABANDONED

    created_by                 TEXT,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalized_at               TIMESTAMPTZ,
    finalized_inspection_id    TEXT REFERENCES inspections(inspection_id)
);

CREATE INDEX IF NOT EXISTS idx_inspection_sessions_status
    ON inspection_sessions(status);

CREATE INDEX IF NOT EXISTS idx_inspection_sessions_product
    ON inspection_sessions(product_id);

CREATE TABLE IF NOT EXISTS session_captures (
    id                       SERIAL PRIMARY KEY,
    session_id                TEXT NOT NULL
                              REFERENCES inspection_sessions(session_id)
                              ON DELETE CASCADE,

    surface_id                 TEXT NOT NULL,
    image_id                   TEXT,
    image_path                 TEXT,
    surface_type                TEXT,

    ocr_fields_json             JSONB,
    surface_observation_json    JSONB,
    evidence_coverage           NUMERIC,

    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_session_captures_session
    ON session_captures(session_id);

ALTER TABLE inspections ADD COLUMN IF NOT EXISTS declarations_json JSONB;
ALTER TABLE inspection_sessions ALTER COLUMN net_quantity_value DROP NOT NULL;
ALTER TABLE inspection_sessions ALTER COLUMN net_quantity_unit DROP NOT NULL;

-- ---------------------------------------------------------------------------
-- Regulation ingestion / amendment drafts (Module 1 integration)
-- ---------------------------------------------------------------------------
-- One row per document ingested through the regulation-ingestion pipeline
-- (backend/lexmetra_rules) or manually authored. Holds the FULL amendment
-- lifecycle state machine already defined in backend/models.py /
-- backend/amendments.py (approval_state: DRAFT -> EXTRACTED -> AI_PARSED ->
-- PENDING_REVIEW -> APPROVED -> SCHEDULED -> ACTIVE -> SUPERSEDED/REJECTED).
-- Rules only ever become part of CURRENT compliance evaluation once a
-- rule_version reaches an ACTIVE approval_state via backend/regulatory --
-- see rule_engine.filter_active_rules() and regulatory/runtime.py.
--
-- approval_state values MUST match backend/models.py's ApprovalState enum
-- exactly (its .value strings are UPPERCASE, e.g. "EXTRACTED") -- that is
-- what backend/db/persistence.py's save_amendment_draft()/
-- update_amendment_draft_state() actually write via _enum_value(), and it
-- matches every other status/state CHECK constraint in this schema (see
-- inspections_status_check, inspection_facts_status_check below, which are
-- also uppercase). This constraint previously listed lowercase values,
-- which never matched anything the application ever writes.
CREATE TABLE IF NOT EXISTS amendment_drafts (
    id                      TEXT PRIMARY KEY,
    source_document_id      TEXT,
    regulation               TEXT,
    approval_state           TEXT NOT NULL,
    -- DRAFT | EXTRACTED | AI_PARSED | PENDING_REVIEW | APPROVED |
    -- SCHEDULED | ACTIVE | SUPERSEDED | REJECTED

    extracted_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at              TIMESTAMPTZ,
    reviewed_by              TEXT,
    activated_at             TIMESTAMPTZ,

    -- Full AmendmentDraft payload (proposed_rule_versions, changes,
    -- extraction_metadata, notes, etc.) -- see backend/models.py. Kept as
    -- one JSONB blob rather than exploded into columns because its shape
    -- is still evolving (Module 1's adapter output) and every field is
    -- already covered by the pydantic model's own validation on read/write.
    payload_json             JSONB NOT NULL,

    created_by               TEXT,

    CONSTRAINT amendment_drafts_state_check CHECK (
        approval_state IN (
            'DRAFT', 'EXTRACTED', 'AI_PARSED', 'PENDING_REVIEW',
            'APPROVED', 'SCHEDULED', 'ACTIVE', 'SUPERSEDED', 'REJECTED'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_amendment_drafts_state
    ON amendment_drafts(approval_state);

CREATE INDEX IF NOT EXISTS idx_amendment_drafts_extracted
    ON amendment_drafts(extracted_at DESC);

CREATE INDEX IF NOT EXISTS idx_amendment_drafts_source_doc
    ON amendment_drafts(source_document_id);

-- Migration guard: if amendment_drafts was created under the legacy lowercase
-- constraint ('draft', 'extracted', ...), migrate existing rows and drop/re-add
-- the constraint so it matches backend/models.py's ApprovalState enum exactly.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_name = 'amendment_drafts'
    ) THEN
        UPDATE amendment_drafts SET approval_state = UPPER(approval_state);

        ALTER TABLE amendment_drafts DROP CONSTRAINT IF EXISTS amendment_drafts_state_check;
        ALTER TABLE amendment_drafts ADD CONSTRAINT amendment_drafts_state_check CHECK (
            approval_state IN (
                'DRAFT', 'EXTRACTED', 'AI_PARSED', 'PENDING_REVIEW',
                'APPROVED', 'SCHEDULED', 'ACTIVE', 'SUPERSEDED', 'REJECTED'
            )
        );
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Regulatory modules, rule versions, and published amendments
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS regulatory_modules (
    module_id           TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    department          TEXT NOT NULL,
    regulation          TEXT NOT NULL,
    jurisdiction        TEXT NOT NULL DEFAULT 'IN',
    status              TEXT NOT NULL DEFAULT 'active',
    metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO regulatory_modules (module_id, name, department, regulation, jurisdiction, status)
VALUES (
    'lmpc',
    'Legal Metrology (Packaged Commodities)',
    'Department of Consumer Affairs',
    'Legal Metrology (Packaged Commodities) Rules, 2011',
    'IN',
    'active'
)
ON CONFLICT (module_id) DO UPDATE SET
    regulation = EXCLUDED.regulation,
    status = EXCLUDED.status;

CREATE TABLE IF NOT EXISTS regulatory_rule_versions (
    rule_version_id             TEXT PRIMARY KEY,
    module_id                   TEXT NOT NULL REFERENCES regulatory_modules(module_id),
    rule_id                     TEXT NOT NULL,
    version                     TEXT NOT NULL,
    effective_from              DATE NOT NULL,
    effective_to                DATE,
    approval_state              TEXT NOT NULL,
    source_document_id          TEXT,
    source_url                  TEXT,
    text                        TEXT,
    conditions_json             JSONB NOT NULL DEFAULT '{}'::jsonb,
    thresholds_json             JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_requirements_json  JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(module_id, rule_id, version)
);

CREATE INDEX IF NOT EXISTS idx_reg_rule_versions_effective
    ON regulatory_rule_versions(module_id, rule_id, effective_from, effective_to);

CREATE INDEX IF NOT EXISTS idx_reg_rule_versions_state
    ON regulatory_rule_versions(approval_state);

-- Stage 1: preserve rich Module 1 extraction after publication.
ALTER TABLE regulatory_rule_versions
    ADD COLUMN IF NOT EXISTS extraction_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Stage 3: durable, queryable ingestion quality reports.
CREATE TABLE IF NOT EXISTS ingestion_reports (
    id                  TEXT PRIMARY KEY,
    document_id         TEXT NOT NULL,
    source_document_id  TEXT,
    amendment_draft_id  TEXT REFERENCES amendment_drafts(id) ON DELETE SET NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    report_json         JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_reports_document
    ON ingestion_reports(document_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_reports_draft
    ON ingestion_reports(amendment_draft_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_reports_generated
    ON ingestion_reports(generated_at DESC);

CREATE TABLE IF NOT EXISTS regulatory_amendments (
    amendment_id        TEXT PRIMARY KEY,
    module_id           TEXT NOT NULL REFERENCES regulatory_modules(module_id),
    source_document_id  TEXT NOT NULL,
    approval_state      TEXT NOT NULL DEFAULT 'DRAFT',
    extracted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by         TEXT,
    approved_at         TIMESTAMPTZ,
    scheduled_for       DATE,
    published_at        TIMESTAMPTZ,
    changes_json        JSONB NOT NULL DEFAULT '[]'::jsonb,
    impact_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reg_amendments_state
    ON regulatory_amendments(module_id, approval_state);


-- ---------------------------------------------------------------------------
-- Regulation ingestion Stage 1/3 additions (additive, idempotent)
-- ---------------------------------------------------------------------------

ALTER TABLE regulatory_rule_versions
    ADD COLUMN IF NOT EXISTS extraction_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS ingestion_reports (
    id                  TEXT PRIMARY KEY,
    document_id         TEXT NOT NULL,
    source_document_id  TEXT,
    amendment_draft_id  TEXT REFERENCES amendment_drafts(id) ON DELETE SET NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    report_json        JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_reports_document
    ON ingestion_reports(document_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_reports_draft
    ON ingestion_reports(amendment_draft_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_reports_generated
    ON ingestion_reports(generated_at DESC);
