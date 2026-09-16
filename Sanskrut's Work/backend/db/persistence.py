"""
PostgreSQL persistence layer for LMPC inspections.

Uses psycopg2 with parameterized SQL and no ORM.

Design goals:
- Keep the database layer small and readable for the SIH MVP.
- Never hard-code a production password into application code.
- Keep transaction handling centralized.
- Serialize the richer inspection schema defensively so DB persistence does not
  become the source of truth for legal logic.
- Preserve compatibility with the existing schema.sql contract while supporting
  richer fact/evidence data when the corresponding columns exist.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    class DummyExtras:
        RealDictCursor = None
    class DummyPsycopg2:
        extras = DummyExtras
        OperationalError = Exception
        DatabaseError = Exception
    psycopg2 = DummyPsycopg2()  # type: ignore


import sys
import sqlite3
import re
from pathlib import Path as _Path

# Allow `import config` whether this module is imported as `db.persistence`
# (backend/ on sys.path) or executed from within backend/db directly.
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
import config  # noqa: E402

# DATABASE_URL is resolved centrally in config.py (env var or backend/.env).
# The fallback there is intentionally localhost-only and must never be used
# as a production credential.
DATABASE_URL = config.DATABASE_URL

_USE_SQLITE: Optional[bool] = None
_SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "lmpc.db"
_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)

SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS users (
    user_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username            TEXT NOT NULL UNIQUE,
    full_name           TEXT,
    hashed_password     TEXT NOT NULL,
    role                TEXT NOT NULL DEFAULT 'inspector',
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    product_id          TEXT PRIMARY KEY,
    category            TEXT,
    first_seen_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inspections (
    inspection_id       TEXT PRIMARY KEY,
    product_id          TEXT REFERENCES products(product_id),
    sale_type           TEXT NOT NULL,
    product_category    TEXT NOT NULL,
    net_quantity_value  REAL,
    net_quantity_unit   TEXT,
    mrp                 REAL,
    overall_status      TEXT NOT NULL,
    exempt_reason       TEXT,
    image_filename      TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed            INTEGER NOT NULL DEFAULT 0,
    reviewer_note       TEXT,
    review_required     INTEGER NOT NULL DEFAULT 0,
    image_path          TEXT,
    created_by          TEXT,
    reviewed_by         TEXT
);

CREATE TABLE IF NOT EXISTS inspection_facts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id       TEXT NOT NULL REFERENCES inspections(inspection_id) ON DELETE CASCADE,
    field               TEXT NOT NULL,
    extracted_value     TEXT,
    status              TEXT NOT NULL,
    confidence          REAL,
    rule_id             TEXT,
    rule_version        TEXT,
    reason              TEXT,
    review_required     INTEGER NOT NULL DEFAULT 0,
    evidence_json       TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_username      TEXT,
    action              TEXT NOT NULL,
    resource_type       TEXT,
    resource_id         TEXT,
    detail              TEXT,
    ip_address          TEXT
);

CREATE TABLE IF NOT EXISTS inspection_sessions (
    session_id              TEXT PRIMARY KEY,
    product_id               TEXT NOT NULL,
    sale_type                 TEXT NOT NULL DEFAULT 'retail',
    product_category          TEXT NOT NULL DEFAULT 'food',
    net_quantity_value         REAL NOT NULL,
    net_quantity_unit          TEXT NOT NULL,
    mrp                        REAL,
    pdp_area_cm2               REAL,
    is_export_only             INTEGER NOT NULL DEFAULT 0,
    retail_bundle_count        INTEGER,
    is_imported_hint           INTEGER,
    status                     TEXT NOT NULL DEFAULT 'OPEN',
    created_by                 TEXT,
    created_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finalized_at               TIMESTAMP,
    finalized_inspection_id    TEXT REFERENCES inspections(inspection_id)
);

CREATE TABLE IF NOT EXISTS session_captures (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id                TEXT NOT NULL REFERENCES inspection_sessions(session_id) ON DELETE CASCADE,
    surface_id                 TEXT NOT NULL,
    image_id                   TEXT,
    image_path                 TEXT,
    surface_type                TEXT,
    ocr_fields_json             TEXT,
    surface_observation_json    TEXT,
    evidence_coverage           REAL,
    created_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_inspections_product ON inspections(product_id);
CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspections(overall_status);
CREATE INDEX IF NOT EXISTS idx_inspections_created ON inspections(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_facts_inspection ON inspection_facts(inspection_id);
CREATE INDEX IF NOT EXISTS idx_facts_field ON inspection_facts(field);
CREATE INDEX IF NOT EXISTS idx_facts_status ON inspection_facts(status);
CREATE INDEX IF NOT EXISTS idx_facts_rule ON inspection_facts(rule_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_occurred ON audit_log(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_inspection_sessions_status ON inspection_sessions(status);
CREATE INDEX IF NOT EXISTS idx_inspection_sessions_product ON inspection_sessions(product_id);
CREATE INDEX IF NOT EXISTS idx_session_captures_session ON session_captures(session_id);
"""


class RowDict(dict):
    """Dictionary-like row that supports both column-name and integer index access."""
    def __init__(self, description, values):
        super().__init__()
        self._keys = [d[0] for d in description] if description else []
        self._values = list(values)
        for k, v in zip(self._keys, self._values):
            self[k] = v

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._values[item]
        return super().__getitem__(item)


class SQLiteCursorWrapper:
    """Adapts an sqlite3 cursor to psycopg2/RealDictCursor conventions."""
    def __init__(self, real_cursor):
        self._cur = real_cursor
        self._results = None
        self._idx = 0

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    def execute(self, sql: str, params=None):
        clean_sql = sql.strip()

        # 1. Handle information_schema.columns queries
        if "information_schema.columns" in clean_sql:
            m = re.search(r"table_name\s*=\s*'([^']+)'", clean_sql, re.IGNORECASE)
            if m:
                table_name = m.group(1)
                pragma_cur = self._cur.connection.cursor()
                rows = pragma_cur.execute(f"PRAGMA table_info({table_name})").fetchall()
                self._results = [[r[1]] for r in rows]
                self._idx = 0
                return self

        # 2. Handle TRUNCATE TABLE
        if clean_sql.upper().startswith("TRUNCATE TABLE") or clean_sql.upper().startswith("TRUNCATE"):
            tables = [
                "session_captures",
                "inspection_sessions",
                "inspection_facts",
                "inspections",
                "products",
                "audit_log",
                "users",
            ]
            for tbl in tables:
                try:
                    self._cur.execute(f"DELETE FROM {tbl}")
                except Exception:
                    pass
            self._results = []
            self._idx = 0
            return self

        # 3. Translate %s to ?
        translated_sql = clean_sql.replace("%s", "?")

        # 4. Translate now() to CURRENT_TIMESTAMP
        translated_sql = re.sub(r"\bnow\(\)", "CURRENT_TIMESTAMP", translated_sql, flags=re.IGNORECASE)

        # 5. Clean parameters
        clean_params = None
        if params is not None:
            clean_params = []
            for p in params:
                if isinstance(p, (dict, list)):
                    clean_params.append(json.dumps(p, default=_json_default))
                elif isinstance(p, bool):
                    clean_params.append(1 if p else 0)
                else:
                    clean_params.append(p)
            clean_params = tuple(clean_params)

        self._results = None
        if clean_params is not None:
            self._cur.execute(translated_sql, clean_params)
        else:
            self._cur.execute(translated_sql)
        return self

    def fetchone(self):
        if self._results is not None:
            if self._idx < len(self._results):
                res = self._results[self._idx]
                self._idx += 1
                return res
            return None
        row = self._cur.fetchone()
        if row is None:
            return None
        return RowDict(self._cur.description, row)

    def fetchall(self):
        if self._results is not None:
            res = self._results[self._idx:]
            self._idx = len(self._results)
            return res
        rows = self._cur.fetchall()
        if not rows:
            return []
        desc = self._cur.description
        return [RowDict(desc, r) for r in rows]

    def __iter__(self):
        return self

    def __next__(self):
        res = self.fetchone()
        if res is None:
            raise StopIteration
        return res

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class SQLiteConnectionWrapper:
    """Context manager wrapper for sqlite3 connection."""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, cursor_factory=None):
        return SQLiteCursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


@contextmanager
def get_conn():
    """
    Open one database connection and commit/rollback as a single transaction.
    Tries PostgreSQL first; falls back cleanly to SQLite if PostgreSQL is unreachable.
    """
    global _USE_SQLITE

    if _USE_SQLITE is not True and hasattr(psycopg2, "connect"):
        try:
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=1)
            _USE_SQLITE = False
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return
        except Exception:
            _USE_SQLITE = True

    # SQLite zero-configuration fallback
    raw_conn = sqlite3.connect(str(_SQLITE_PATH))
    wrapper = SQLiteConnectionWrapper(raw_conn)
    try:
        yield wrapper
        wrapper.commit()
    except Exception:
        wrapper.rollback()
        raise
    finally:
        wrapper.close()


def init_schema() -> None:
    """
    Initialize database schema (PostgreSQL schema.sql or SQLite DDL)
    and ensure default admin account exists.
    """
    global _USE_SQLITE
    with get_conn() as conn:
        with conn.cursor() as cur:
            if _USE_SQLITE:
                for statement in SQLITE_DDL.split(";"):
                    s = statement.strip()
                    if s:
                        cur._cur.execute(s)
            else:
                schema_path = Path(__file__).with_name("schema.sql")
                if schema_path.exists():
                    schema_sql = schema_path.read_text(encoding="utf-8")
                    if schema_sql.strip():
                        cur.execute(schema_sql)

            # Ensure bootstrap admin user exists (username: admin, password: password123)
            cur.execute("SELECT 1 FROM users WHERE username = %s", ("admin",))
            if not cur.fetchone():
                try:
                    from auth import hash_password
                    cur.execute(
                        """
                        INSERT INTO users (username, hashed_password, role, full_name)
                        VALUES (%s, %s, %s, %s)
                        """,
                        ("admin", hash_password("password123"), "admin", "LMPC System Administrator")
                    )
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _enum_value(value: Any) -> Any:
    """Return Enum.value when present, otherwise the original value."""
    return value.value if hasattr(value, "value") else value


def _json_default(value: Any) -> Any:
    """
    JSON fallback for Decimal/Enum/Pydantic-like objects.

    This is only for evidence/metadata persistence. Legal decisions remain
    represented by their explicit relational fields.
    """
    if hasattr(value, "value"):
        return value.value

    if hasattr(value, "model_dump"):
        return value.model_dump()

    if hasattr(value, "dict"):
        return value.dict()

    return str(value)


def _json_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            default=_json_default,
        )
    except (TypeError, ValueError):
        return json.dumps(str(value), ensure_ascii=False)


def _product_id_from_inspection(inspection: Any) -> str:
    """
    Current inspection IDs are generated as '<product_id>:scan-<uuid>'.

    If a future schema carries an explicit product_id, prefer that.
    """
    explicit = getattr(inspection, "product_id", None)
    if explicit:
        return str(explicit)

    inspection_id = str(getattr(inspection, "inspection_id", ""))
    return inspection_id.split(":", 1)[0] if ":" in inspection_id else inspection_id


def _inspection_status(inspection: Any) -> Any:
    summary = getattr(inspection, "summary", None)

    if summary is not None:
        status = getattr(summary, "overall_status", None)
        if status is not None:
            return _enum_value(status)

    return _enum_value(getattr(inspection, "overall_status", None))


def _inspection_review_required(inspection: Any) -> bool:
    summary = getattr(inspection, "summary", None)
    if summary is not None:
        value = getattr(summary, "review_required", None)
        if value is not None:
            return bool(value)

    value = getattr(inspection, "review_required", None)
    if value is not None:
        return bool(value)

    for fact in getattr(inspection, "facts", []) or []:
        if bool(getattr(fact, "review_required", False)):
            return True

    for finding in getattr(inspection, "findings", []) or []:
        if bool(getattr(finding, "review_required", False)):
            return True

    return False


def _inspection_exempt_reason(inspection: Any) -> Optional[str]:
    return getattr(inspection, "exempt_reason", None)


def _inspection_quantity(inspection: Any) -> tuple[Any, Any]:
    value = getattr(inspection, "package_weight_or_volume", None)
    unit = getattr(inspection, "package_weight_unit", None)

    if value is None:
        value = getattr(inspection, "net_quantity_value", None)

    if unit is None:
        unit = getattr(inspection, "net_quantity_unit", None)

    return value, unit


def _fact_value(fact: Any) -> Any:
    """
    Prefer the current richer ExtractedFact representation, with fallback to
    the legacy `extracted_value` property.
    """
    value = getattr(fact, "extracted_value", None)
    if value is not None:
        return value

    value = getattr(fact, "value", None)
    if value is not None:
        return value

    return None


def _fact_rule_id(fact: Any) -> Optional[str]:
    return getattr(fact, "rule_id", None)


def _fact_rule_version(fact: Any) -> Optional[str]:
    return getattr(fact, "rule_version", None)


def _fact_reason(fact: Any) -> Optional[str]:
    return getattr(fact, "reason", None)


def _fact_status(fact: Any) -> Any:
    return _enum_value(getattr(fact, "status", None))


def _fact_confidence(fact: Any) -> Optional[float]:
    value = getattr(fact, "confidence", None)
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fact_review_required(fact: Any) -> bool:
    return bool(getattr(fact, "review_required", False))


def _fact_evidence_payload(fact: Any) -> Optional[str]:
    evidence = getattr(fact, "evidence", None)
    if evidence is None:
        return None
    return _json_or_none(evidence)


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_inspection(
    inspection: Any,
    image_filename: Optional[str] = None,
    mrp: Optional[float] = None,
) -> None:
    """
    Persist one ProductInspection atomically.

    The relational tables remain the primary query surface:
      products
      inspections
      inspection_facts

    Rich evidence is serialized into `evidence_json` when that column exists in
    the database schema. The function first checks available columns so an
    older MVP schema can still be used during development.
    """
    inspection_id = str(inspection.inspection_id)
    product_id = _product_id_from_inspection(inspection)

    category = getattr(inspection, "product_category", None)
    sale_type = getattr(inspection, "sale_type", None)

    quantity_value, quantity_unit = _inspection_quantity(inspection)

    overall_status = _inspection_status(inspection)
    exempt_reason = _inspection_exempt_reason(inspection)
    review_required = _inspection_review_required(inspection)

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Product identity is intentionally lightweight here. A future
            # normalized product table can carry richer identity metadata.
            cur.execute(
                """
                INSERT INTO products (product_id, category)
                VALUES (%s, %s)
                ON CONFLICT (product_id) DO UPDATE SET
                    category = COALESCE(EXCLUDED.category, products.category)
                """,
                (product_id, category),
            )

            # Keep the existing core schema contract.
            cur.execute(
                """
                INSERT INTO inspections
                    (
                        inspection_id,
                        product_id,
                        sale_type,
                        product_category,
                        net_quantity_value,
                        net_quantity_unit,
                        mrp,
                        overall_status,
                        exempt_reason,
                        image_filename
                    )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (inspection_id) DO UPDATE SET
                    product_id = EXCLUDED.product_id,
                    sale_type = EXCLUDED.sale_type,
                    product_category = EXCLUDED.product_category,
                    net_quantity_value = EXCLUDED.net_quantity_value,
                    net_quantity_unit = EXCLUDED.net_quantity_unit,
                    mrp = EXCLUDED.mrp,
                    overall_status = EXCLUDED.overall_status,
                    exempt_reason = EXCLUDED.exempt_reason,
                    image_filename = COALESCE(
                        EXCLUDED.image_filename,
                        inspections.image_filename
                    )
                """,
                (
                    inspection_id,
                    product_id,
                    sale_type,
                    category,
                    quantity_value,
                    quantity_unit,
                    mrp,
                    overall_status,
                    exempt_reason,
                    image_filename,
                ),
            )

            # Replace fact rows on re-save. This keeps repeated inspection IDs
            # deterministic during review/reprocessing.
            cur.execute(
                "DELETE FROM inspection_facts WHERE inspection_id = %s",
                (inspection_id,),
            )

            facts = getattr(inspection, "facts", []) or []

            # Detect optional richer columns once. This lets us preserve
            # compatibility with the original three-table MVP schema while
            # allowing evidence JSON in an upgraded schema.
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'inspection_facts'
                """
            )
            fact_columns = {
                row[0]
                for row in cur.fetchall()
            }

            has_evidence_json = "evidence_json" in fact_columns

            for fact in facts:
                field = str(getattr(fact, "field", ""))

                base_values = (
                    inspection_id,
                    field,
                    _fact_value(fact),
                    _fact_status(fact),
                    _fact_confidence(fact),
                    _fact_rule_id(fact),
                    _fact_rule_version(fact),
                    _fact_reason(fact),
                    _fact_review_required(fact),
                )

                if has_evidence_json:
                    cur.execute(
                        """
                        INSERT INTO inspection_facts
                            (
                                inspection_id,
                                field,
                                extracted_value,
                                status,
                                confidence,
                                rule_id,
                                rule_version,
                                reason,
                                review_required,
                                evidence_json
                            )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        base_values + (_fact_evidence_payload(fact),),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO inspection_facts
                            (
                                inspection_id,
                                field,
                                extracted_value,
                                status,
                                confidence,
                                rule_id,
                                rule_version,
                                reason,
                                review_required
                            )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        base_values,
                    )

            # If the upgraded inspections table has a review_required column,
            # persist the aggregate state as well. Otherwise the existing
            # inspection_facts review flags remain the source for list filters.
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'inspections'
                """
            )
            inspection_columns = {
                row[0]
                for row in cur.fetchall()
            }

            if "review_required" in inspection_columns:
                cur.execute(
                    """
                    UPDATE inspections
                    SET review_required = %s
                    WHERE inspection_id = %s
                    """,
                    (review_required, inspection_id),
                )


# ---------------------------------------------------------------------------
# Read/list
# ---------------------------------------------------------------------------

def list_inspections(
    limit: int = 50,
    status: Optional[str] = None,
    needs_review: Optional[bool] = None,
) -> list[dict]:
    """
    Return newest inspections first.

    `needs_review=False` deliberately means "no review-required filter", which
    preserves the original endpoint semantics. The frontend can use
    needs_review=true for the review queue.
    """
    safe_limit = max(1, min(int(limit), 200))

    query = """
        SELECT *
        FROM inspections
    """
    conditions: list[str] = []
    params: list[Any] = []

    if status:
        conditions.append("overall_status = %s")
        params.append(status)

    if needs_review is True:
        conditions.append(
            """
            inspection_id IN (
                SELECT inspection_id
                FROM inspection_facts
                WHERE review_required = TRUE
            )
            """
        )

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(safe_limit)

    with get_conn() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]


def get_inspection_detail(inspection_id: str) -> Optional[dict]:
    """
    Return one inspection plus all persisted field evidence.
    """
    with get_conn() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                """
                SELECT *
                FROM inspections
                WHERE inspection_id = %s
                """,
                (inspection_id,),
            )
            inspection = cur.fetchone()

            if not inspection:
                return None

            cur.execute(
                """
                SELECT *
                FROM inspection_facts
                WHERE inspection_id = %s
                ORDER BY id ASC
                """,
                (inspection_id,),
            )
            inspection["facts"] = [
                dict(row) for row in cur.fetchall()
            ]

            # Decode optional JSON evidence so the frontend receives structured
            # evidence rather than a JSON string. psycopg2 auto-decodes JSONB
            # columns to native Python objects, so handle both a raw string
            # and an already-decoded list/dict defensively.
            for fact in inspection["facts"]:
                raw_evidence = fact.get("evidence_json")
                if isinstance(raw_evidence, str):
                    try:
                        fact["evidence"] = json.loads(raw_evidence)
                    except (TypeError, ValueError):
                        fact["evidence"] = None
                elif raw_evidence is not None:
                    fact["evidence"] = raw_evidence

            return dict(inspection)


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

def mark_reviewed(
    inspection_id: str,
    note: str = "",
    reviewed_by: Optional[str] = None,
) -> bool:
    """
    Mark an existing inspection as reviewed.

    Returns True if a row was updated and False if the inspection does not
    exist. The API layer can turn False into a 404.
    """
    clean_note = (note or "").strip()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'inspections'
                """
            )
            cols = {row[0] for row in cur.fetchall()}

            if reviewed_by is not None and "reviewed_by" in cols:
                cur.execute(
                    """
                    UPDATE inspections
                    SET reviewed = TRUE,
                        reviewer_note = %s,
                        reviewed_by = %s
                    WHERE inspection_id = %s
                    """,
                    (clean_note, reviewed_by, inspection_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE inspections
                    SET reviewed = TRUE,
                        reviewer_note = %s
                    WHERE inspection_id = %s
                    """,
                    (clean_note, inspection_id),
                )
            return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Product history
# ---------------------------------------------------------------------------

def product_history(
    product_id: str,
    limit: int = 20,
) -> list[dict]:
    safe_limit = max(1, min(int(limit), 100))

    with get_conn() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                """
                SELECT
                    inspection_id,
                    overall_status,
                    mrp,
                    net_quantity_value,
                    net_quantity_unit,
                    created_at,
                    reviewed,
                    reviewer_note
                FROM inspections
                WHERE product_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (product_id, safe_limit),
            )
            return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Users / authentication
# ---------------------------------------------------------------------------

def create_user(
    username: str,
    hashed_password: str,
    role: str = "inspector",
    full_name: Optional[str] = None,
) -> dict:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO users (username, hashed_password, role, full_name)
                VALUES (%s, %s, %s, %s)
                RETURNING user_id, username, full_name, role, is_active, created_at
                """,
                (username, hashed_password, role, full_name),
            )
            return dict(cur.fetchone())


def get_user_by_username(username: str) -> Optional[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT user_id, username, full_name, hashed_password, role,
                       is_active, created_at
                FROM users
                WHERE username = %s
                """,
                (username,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def list_users() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT user_id, username, full_name, role, is_active, created_at
                FROM users
                ORDER BY created_at ASC
                """
            )
            return [dict(row) for row in cur.fetchall()]


def any_user_exists() -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users LIMIT 1")
            return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

def record_audit_event(
    action: str,
    actor_username: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Append one audit-log entry. Never raises to the caller: audit logging must
    not be able to break the primary inspection workflow.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_log
                        (actor_username, action, resource_type, resource_id, detail, ip_address)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (actor_username, action, resource_type, resource_id, detail, ip_address),
                )
    except Exception:
        pass


def list_audit_log(limit: int = 100) -> list[dict]:
    safe_limit = max(1, min(int(limit), 500))
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM audit_log
                ORDER BY occurred_at DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            return [dict(row) for row in cur.fetchall()]


def set_inspection_attribution(
    inspection_id: str,
    created_by: Optional[str] = None,
    image_path: Optional[str] = None,
) -> None:
    """Attach who ran a scan and where the original evidence image is stored."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'inspections'
                """
            )
            cols = {row[0] for row in cur.fetchall()}
            sets, params = [], []
            if created_by is not None and "created_by" in cols:
                sets.append("created_by = %s")
                params.append(created_by)
            if image_path is not None and "image_path" in cols:
                sets.append("image_path = %s")
                params.append(image_path)
            if not sets:
                return
            params.append(inspection_id)
            cur.execute(
                f"UPDATE inspections SET {', '.join(sets)} WHERE inspection_id = %s",
                params,
            )


# ---------------------------------------------------------------------------
# Multi-surface inspection sessions
# ---------------------------------------------------------------------------

def create_session(
    session_id: str,
    product_id: str,
    sale_type: str,
    product_category: str,
    net_quantity_value: float,
    net_quantity_unit: str,
    mrp: Optional[float] = None,
    pdp_area_cm2: Optional[float] = None,
    is_export_only: bool = False,
    retail_bundle_count: Optional[int] = None,
    is_imported_hint: Optional[bool] = None,
    created_by: Optional[str] = None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO inspection_sessions
                    (session_id, product_id, sale_type, product_category,
                     net_quantity_value, net_quantity_unit, mrp, pdp_area_cm2,
                     is_export_only, retail_bundle_count, is_imported_hint,
                     created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id, product_id, sale_type, product_category,
                    net_quantity_value, net_quantity_unit, mrp, pdp_area_cm2,
                    is_export_only, retail_bundle_count, is_imported_hint,
                    created_by,
                ),
            )


def get_session(session_id: str) -> Optional[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM inspection_sessions WHERE session_id = %s",
                (session_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def add_session_capture(
    session_id: str,
    surface_id: str,
    image_id: Optional[str],
    image_path: Optional[str],
    surface_type: Optional[str],
    ocr_fields: Dict[str, Any],
    surface_observation: Dict[str, Any],
    evidence_coverage: float,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO session_captures
                    (session_id, surface_id, image_id, image_path, surface_type,
                     ocr_fields_json, surface_observation_json, evidence_coverage)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id, surface_id, image_id, image_path, surface_type,
                    _json_or_none(ocr_fields), _json_or_none(surface_observation),
                    evidence_coverage,
                ),
            )


def list_session_captures(session_id: str) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM session_captures
                WHERE session_id = %s
                ORDER BY id ASC
                """,
                (session_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]
            for row in rows:
                # psycopg2 decodes JSONB columns to native Python objects
                # automatically. Handle both that case and a raw JSON string
                # defensively, rather than assuming one representation.
                raw_fields = row.get("ocr_fields_json")
                if isinstance(raw_fields, str):
                    try:
                        row["ocr_fields"] = json.loads(raw_fields)
                    except (TypeError, ValueError):
                        row["ocr_fields"] = {}
                elif raw_fields is not None:
                    row["ocr_fields"] = raw_fields
                else:
                    row["ocr_fields"] = {}

                raw_obs = row.get("surface_observation_json")
                if isinstance(raw_obs, str):
                    try:
                        row["surface_observation"] = json.loads(raw_obs)
                    except (TypeError, ValueError):
                        row["surface_observation"] = {}
                elif raw_obs is not None:
                    row["surface_observation"] = raw_obs
                else:
                    row["surface_observation"] = {}
            return rows


def finalize_session(session_id: str, inspection_id: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE inspection_sessions
                SET status = 'FINALIZED',
                    finalized_at = now(),
                    finalized_inspection_id = %s
                WHERE session_id = %s AND status = 'OPEN'
                """,
                (inspection_id, session_id),
            )
            return cur.rowcount > 0


def truncate_all_data() -> None:
    """
    Danger: wipes every application data table. Intended ONLY for automated
    test runs against a disposable dev/test database (see tests/conftest.py).
    Never call this from application/API code.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE TABLE
                    session_captures,
                    inspection_sessions,
                    inspection_facts,
                    inspections,
                    products,
                    audit_log,
                    users
                RESTART IDENTITY CASCADE
                """
            )


def list_sessions(status: Optional[str] = None, limit: int = 50) -> list[dict]:
    safe_limit = max(1, min(int(limit), 200))
    query = "SELECT * FROM inspection_sessions"
    params: list[Any] = []
    if status:
        query += " WHERE status = %s"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(safe_limit)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
