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
    review_required     BOOLEAN NOT NULL DEFAULT FALSE
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
END $$;
