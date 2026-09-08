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

import psycopg2
import psycopg2.extras


# In development, DATABASE_URL should normally be supplied by the environment.
# The fallback is intentionally localhost-only and must never be used as a
# production credential.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://lmpc_app:lmpc_dev_pw@localhost:5432/lmpc",
)


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
            # evidence rather than a JSON string.
            for fact in inspection["facts"]:
                if "evidence_json" in fact and fact["evidence_json"]:
                    try:
                        fact["evidence"] = json.loads(fact["evidence_json"])
                    except (TypeError, ValueError):
                        fact["evidence"] = None

            return dict(inspection)


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

def mark_reviewed(
    inspection_id: str,
    note: str = "",
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
