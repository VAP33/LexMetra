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
from typing import Any, Dict, Iterable, List, Optional

import psycopg2
import psycopg2.extras

import sys
from pathlib import Path as _Path

# Allow `import config` whether this module is imported as `db.persistence`
# (backend/ on sys.path) or executed from within backend/db directly.
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
import config  # noqa: E402

# DATABASE_URL is resolved centrally in config.py (env var or backend/.env).
# The fallback there is intentionally localhost-only and must never be used
# as a production credential.
DATABASE_URL = config.DATABASE_URL


@contextmanager
def get_conn():
    """
    Open one database connection and commit/rollback as a single transaction.
    """
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    """
    Initialize the database from backend/db/schema.sql.

    schema.sql is intentionally kept as the database definition source rather
    than duplicating CREATE TABLE statements here.
    """
    schema_path = Path(__file__).with_name("schema.sql")
    if not schema_path.exists():
        raise FileNotFoundError(f"Database schema not found: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")

    if not schema_sql.strip():
        raise RuntimeError("Database schema.sql is empty.")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)


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
    raw_ocr_lines: Optional[List[Dict[str, Any]]] = None,
    barcode_data: Optional[str] = None,
) -> None:
    """
    raw_ocr_lines and barcode_data are additive (nullable columns - see
    schema.sql migration). raw_ocr_lines preserves every OCR-engine text
    fragment (not just the classified fields) so a LATER capture in this
    session can attempt scoped cross-image split-declaration reconstruction
    against this capture's un-labelled fragments (evidence_fusion.
    reconstruct_split_fields needs the raw lines, not just the already-
    classified fields, to find a bare completing fragment).
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO session_captures
                    (session_id, surface_id, image_id, image_path, surface_type,
                     ocr_fields_json, surface_observation_json, evidence_coverage,
                     raw_ocr_lines_json, barcode_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id, surface_id, image_id, image_path, surface_type,
                    _json_or_none(ocr_fields), _json_or_none(surface_observation),
                    evidence_coverage, _json_or_none(raw_ocr_lines), barcode_data,
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

                # raw_ocr_lines_json is optional - older rows (written before
                # this migration) will simply have NULL here.
                raw_lines = row.get("raw_ocr_lines_json")
                if isinstance(raw_lines, str):
                    try:
                        row["raw_ocr_lines"] = json.loads(raw_lines)
                    except (TypeError, ValueError):
                        row["raw_ocr_lines"] = []
                elif raw_lines is not None:
                    row["raw_ocr_lines"] = raw_lines
                else:
                    row["raw_ocr_lines"] = []
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
