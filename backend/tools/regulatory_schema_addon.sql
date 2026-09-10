-- -------------------------------------------------------------------------
-- Regulatory knowledge / amendment platform
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS regulatory_modules (
    module_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    regulation TEXT NOT NULL,
    jurisdiction TEXT NOT NULL DEFAULT 'IN',
    status TEXT NOT NULL DEFAULT 'experimental',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS regulatory_rule_versions (
    rule_version_id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL REFERENCES regulatory_modules(module_id),
    rule_id TEXT NOT NULL,
    version TEXT NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    approval_state TEXT NOT NULL,
    source_document_id TEXT,
    source_url TEXT,
    text TEXT,
    conditions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    thresholds_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_requirements_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(module_id, rule_id, version)
);
CREATE INDEX IF NOT EXISTS idx_reg_rule_versions_effective ON regulatory_rule_versions(module_id, rule_id, effective_from, effective_to);
CREATE TABLE IF NOT EXISTS regulatory_documents (
    document_id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL REFERENCES regulatory_modules(module_id),
    title TEXT NOT NULL,
    document_version TEXT NOT NULL,
    source_url TEXT,
    effective_from DATE,
    effective_to DATE,
    approval_state TEXT NOT NULL DEFAULT 'DRAFT',
    sha256 TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS regulatory_knowledge_chunks (
    chunk_id TEXT PRIMARY KEY,
    module TEXT NOT NULL,
    department TEXT NOT NULL,
    regulation TEXT NOT NULL,
    document_id TEXT NOT NULL,
    document_version TEXT NOT NULL,
    rule_version TEXT,
    rule_id TEXT,
    effective_from DATE NOT NULL,
    effective_to DATE,
    index_version TEXT NOT NULL,
    page INTEGER,
    section TEXT,
    clause TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    commodity TEXT,
    jurisdiction TEXT NOT NULL DEFAULT 'IN',
    text TEXT NOT NULL,
    source_url TEXT,
    source_reference TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reg_chunks_filter ON regulatory_knowledge_chunks(module, department, jurisdiction, effective_from, effective_to);
CREATE INDEX IF NOT EXISTS idx_reg_chunks_rule ON regulatory_knowledge_chunks(rule_id);
CREATE TABLE IF NOT EXISTS regulatory_amendments (
    amendment_id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL REFERENCES regulatory_modules(module_id),
    source_document_id TEXT NOT NULL,
    approval_state TEXT NOT NULL DEFAULT 'DRAFT',
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    scheduled_for DATE,
    published_at TIMESTAMPTZ,
    changes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    impact_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reg_amendments_state ON regulatory_amendments(module_id, approval_state, scheduled_for);
