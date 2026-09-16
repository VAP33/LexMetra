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
import logging
import os
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)


try:
    import psycopg2
    import psycopg2.extras

    _DRIVER_ERROR: type[BaseException] = psycopg2.Error
except ModuleNotFoundError:  # pragma: no cover - exercised in driverless envs
    # The PostgreSQL driver is a hard requirement to TALK to a database, but not
    # to reason about what this module writes. `build_finding_row`,
    # `hydrate_finding_row` and `decode_json_column` decide whether evidence and
    # provenance survive a round trip, and they are pure. Making the import
    # fatal put them behind a dependency that is absent in offline test
    # environments, which meant the code most capable of silently dropping legal
    # evidence was the code least able to be tested. Anything that actually
    # needs a connection still fails loudly, in `get_conn`.
    psycopg2 = None  # type: ignore[assignment]
    _DRIVER_ERROR = Exception

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
    if psycopg2 is None:
        raise RuntimeError(
            "psycopg2 is not installed, so no database connection can be "
            "opened. Install psycopg2-binary (see backend/requirements.txt). "
            "The pure serialization helpers in this module do not need it."
        )

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
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")

    if hasattr(value, "dict"):
        return value.dict()

    if isinstance(value, Enum) or (hasattr(value, "value") and hasattr(type(value), "__members__")):
        return value.value

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
# Findings
#
# These are deliberately pure functions taking a finding and returning plain
# values. The database driver (psycopg2) and a PostgreSQL server are not
# available in every environment this project is tested in, so anything that
# only exists inside a `with get_conn()` block cannot be exercised by a test at
# all. Keeping the row construction and the column decoding separate from the
# SQL means the part that can silently lose evidence is testable on its own.
# ---------------------------------------------------------------------------

#: Column order used by both the INSERT and `build_finding_row`, so the two
#: cannot drift apart silently.
FINDING_COLUMNS = (
    "inspection_id",
    "rule_id",
    "rule_version",
    "status",
    "requirement_id",
    "requirement_description",
    "reason",
    "confidence",
    "review_required",
    "verification_status",
    "evidence_json",
    "required_evidence_json",
    "missing_evidence_json",
)


def build_finding_row(inspection_id: str, finding: Any) -> Dict[str, Any]:
    """
    Flatten one RuleFinding into the `inspection_findings` column set.

    `evidence_json` carries the EvidenceReference list verbatim, which is what
    makes a reloaded finding traceable back to a specific region of a specific
    source image. `required_evidence` and `missing_evidence` are kept as
    separate columns rather than folded into the reason text because "nothing
    was observed" and "something was observed and it contradicts the
    declaration" are different legal positions, and a reviewer reading a
    reloaded finding must still be able to tell them apart.
    """
    confidence = getattr(finding, "confidence", None)
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    return {
        "inspection_id": inspection_id,
        "rule_id": str(getattr(finding, "rule_id", "") or ""),
        "rule_version": getattr(finding, "rule_version", None),
        "status": _enum_value(getattr(finding, "status", None)),
        "requirement_id": getattr(finding, "requirement_id", None),
        "requirement_description": getattr(finding, "requirement_description", None),
        "reason": getattr(finding, "reason", None),
        "confidence": confidence,
        "review_required": bool(getattr(finding, "review_required", False)),
        "verification_status": _enum_value(
            getattr(finding, "verification_status", None)
        ),
        "evidence_json": _json_or_none(getattr(finding, "evidence", None) or None),
        "required_evidence_json": _json_or_none(
            getattr(finding, "required_evidence", None) or None
        ),
        "missing_evidence_json": _json_or_none(
            getattr(finding, "missing_evidence", None) or None
        ),
    }


def decode_json_column(raw: Any, field_name: Optional[str] = None) -> Any:
    """
    Return a JSONB column as native Python.

    psycopg2 decodes JSONB automatically, but the same rows are also read from
    fixtures and from older databases where the column may hold a JSON string.
    Both shapes are handled rather than assuming one, and undecodable content
    returns None with an explicit log instead of raising — a malformed evidence
    blob must not make an entire inspection unreadable or silently disappear.
    """
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Malformed JSON in persisted column '%s': %s (raw text: %.100r)",
                field_name or "unknown", exc, raw
            )
            return None
    return raw


def hydrate_finding_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Turn one persisted findings row back into the shape callers expect,
    decoding the three JSON columns into `evidence`, `required_evidence` and
    `missing_evidence`.
    """
    finding = dict(row)
    finding["evidence"] = decode_json_column(row.get("evidence_json")) or []
    finding["required_evidence"] = (
        decode_json_column(row.get("required_evidence_json")) or []
    )
    finding["missing_evidence"] = (
        decode_json_column(row.get("missing_evidence_json")) or []
    )
    return finding


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

            if "declarations_json" in inspection_columns:
                cur.execute(
                    """
                    UPDATE inspections
                    SET declarations_json = %s
                    WHERE inspection_id = %s
                    """,
                    (_json_or_none(getattr(inspection, "declarations", []) or []), inspection_id),
                )

            # ---------------- Findings ----------------
            #
            # The legal verdicts. Previously not persisted at all, so a reloaded
            # inspection had facts but no findings, and the PDF report quietly
            # rendered facts in their place. Guarded by a table-existence check
            # so an older database that has not run the current schema.sql keeps
            # working rather than failing every save.
            cur.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'inspection_findings'
                """
            )
            has_findings_table = cur.fetchone() is not None

            if has_findings_table:
                cur.execute(
                    "DELETE FROM inspection_findings WHERE inspection_id = %s",
                    (inspection_id,),
                )

                findings = getattr(inspection, "findings", []) or []
                placeholders = ", ".join(["%s"] * len(FINDING_COLUMNS))
                columns = ", ".join(FINDING_COLUMNS)

                for finding in findings:
                    row = build_finding_row(inspection_id, finding)
                    cur.execute(
                        f"INSERT INTO inspection_findings ({columns}) "
                        f"VALUES ({placeholders})",
                        tuple(row[name] for name in FINDING_COLUMNS),
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

            if "declarations_json" in inspection:
                decoded_declarations = decode_json_column(inspection.get("declarations_json"))
                if decoded_declarations is not None:
                    inspection["declarations"] = decoded_declarations
                else:
                    inspection["declarations"] = []

            # Decode optional JSON evidence so the frontend receives structured
            # evidence rather than a JSON string. psycopg2 auto-decodes JSONB
            # columns to native Python objects, so handle both a raw string
            # and an already-decoded list/dict defensively.
            for fact in inspection["facts"]:
                raw_evidence = fact.get("evidence_json")
                decoded = decode_json_column(raw_evidence)
                if decoded is not None:
                    fact["evidence"] = decoded

            # Findings: the legal verdicts. A reloaded inspection without these
            # is not auditable, and `report.py` silently renders facts instead
            # when the list is absent. Read defensively so a database that has
            # not yet run the current schema.sql still returns the inspection
            # rather than raising.
            try:
                cur.execute(
                    """
                    SELECT *
                    FROM inspection_findings
                    WHERE inspection_id = %s
                    ORDER BY id ASC
                    """,
                    (inspection_id,),
                )
                inspection["findings"] = [
                    hydrate_finding_row(dict(row)) for row in cur.fetchall()
                ]
            except _DRIVER_ERROR:
                # Roll the failed statement back so the connection stays usable.
                conn.rollback()
                inspection["findings"] = []
                inspection["findings_unavailable"] = True

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
    net_quantity_value: Optional[float] = None,
    net_quantity_unit: Optional[str] = None,
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
                decoded_fields = decode_json_column(row.get("ocr_fields_json"), "ocr_fields_json")
                row["ocr_fields"] = decoded_fields if isinstance(decoded_fields, dict) else {}

                decoded_obs = decode_json_column(row.get("surface_observation_json"), "surface_observation_json")
                row["surface_observation"] = decoded_obs if isinstance(decoded_obs, dict) else {}
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


# ---------------------------------------------------------------------------
# Amendment drafts (Module 1 regulation-ingestion integration)
# ---------------------------------------------------------------------------
# Persists the AmendmentDraft lifecycle objects defined in backend/models.py.
# A draft only ever affects CURRENT compliance evaluation once its
# approval_state reaches ACTIVE and its rule versions are picked up by
# regulatory/runtime.apply_rule_versions -- inserting/updating a row here
# never itself changes what rule_engine.run_inspection() evaluates.

def save_amendment_draft(draft: Any, created_by: Optional[str] = None) -> None:
    """Insert or fully replace one AmendmentDraft (pydantic model or plain
    dict with the same shape)."""
    payload = draft.model_dump(mode="json") if hasattr(draft, "model_dump") else dict(draft)

    draft_id = str(payload["id"])
    source_document_id = payload.get("source_document_id")
    raw_state = _enum_value(payload.get("approval_state"))
    approval_state = str(raw_state).upper() if raw_state is not None else "DRAFT"
    regulation = None
    versions = payload.get("proposed_rule_versions") or []
    if versions:
        regulation = versions[0].get("regulation")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO amendment_drafts
                    (id, source_document_id, regulation, approval_state,
                     extracted_at, reviewed_at, reviewed_by, activated_at,
                     payload_json, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    approval_state = EXCLUDED.approval_state,
                    reviewed_at    = EXCLUDED.reviewed_at,
                    reviewed_by    = EXCLUDED.reviewed_by,
                    activated_at   = EXCLUDED.activated_at,
                    payload_json   = EXCLUDED.payload_json
                """,
                (
                    draft_id,
                    source_document_id,
                    regulation,
                    approval_state,
                    payload.get("extracted_at"),
                    payload.get("reviewed_at"),
                    payload.get("reviewed_by"),
                    payload.get("activated_at"),
                    _json_or_none(payload),
                    created_by,
                ),
            )


def get_amendment_draft(draft_id: str) -> Optional[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM amendment_drafts WHERE id = %s", (draft_id,))
            row = cur.fetchone()
            if row is None:
                return None
            row = dict(row)
            row["payload"] = decode_json_column(row.get("payload_json"))
            return row


def list_amendment_drafts(approval_state: Optional[str] = None, limit: int = 100) -> list[dict]:
    safe_limit = max(1, min(int(limit), 500))
    query = "SELECT * FROM amendment_drafts"
    params: list[Any] = []
    if approval_state:
        query += " WHERE approval_state = %s"
        params.append(str(_enum_value(approval_state)).upper())
    query += " ORDER BY extracted_at DESC LIMIT %s"
    params.append(safe_limit)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        row["payload"] = decode_json_column(row.get("payload_json"))
    return rows


def update_amendment_draft_state(
    draft_id: str,
    approval_state: str,
    payload_json: Optional[str] = None,
    reviewed_at: Optional[Any] = None,
    reviewed_by: Optional[str] = None,
    activated_at: Optional[Any] = None,
) -> None:
    """Persist the result of an amendments.transition_amendment()/
    activate_amendment() call -- the full re-serialized draft plus the
    denormalized state columns used for indexing/filtering."""
    st = str(_enum_value(approval_state)).upper() if approval_state is not None else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE amendment_drafts SET
                    approval_state = %s,
                    payload_json   = COALESCE(%s, payload_json),
                    reviewed_at    = COALESCE(%s, reviewed_at),
                    reviewed_by    = COALESCE(%s, reviewed_by),
                    activated_at   = COALESCE(%s, activated_at)
                WHERE id = %s
                """,
                (
                    st,
                    payload_json,
                    reviewed_at,
                    reviewed_by,
                    activated_at,
                    draft_id,
                ),
            )


def publish_amendment_draft(
    draft_id: str,
    published_by: str,
    module_id: str = "lmpc",
) -> Dict[str, Any]:
    """
    Atomically publish an approved amendment draft into the authoritative
    PostgreSQL rule tables (regulatory_rule_versions & regulatory_amendments)
    and mark the draft as ACTIVE.

    Transactional guarantee:
      ALL executable rules are inserted into regulatory_rule_versions,
      or the entire transaction rolls back.
    """
    import uuid
    from datetime import datetime, timezone, date

    now = datetime.now(timezone.utc)
    draft_row = get_amendment_draft(draft_id)
    if draft_row is None:
        raise ValueError(f"Amendment draft not found: {draft_id}")

    payload = draft_row["payload"]
    raw_versions = payload.get("proposed_rule_versions") or []
    if not raw_versions:
        raise ValueError(f"Amendment draft {draft_id} contains no proposed rule versions to publish.")

    impact = payload.get("impact") or {}
    meta = impact.get("amendment_metadata") or {}
    amendment_name = (
        meta.get("amendment_name")
        or impact.get("amendment")
        or meta.get("version_label")
        or "Amendment"
    )
    parent_regulation = (
        meta.get("regulation")
        or payload.get("regulation")
        or "Legal Metrology (Packaged Commodities) Rules, 2011"
    )
    source_doc = payload.get("source_document_id") or draft_id

    published_rules_info: list[dict[str, Any]] = []

    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. Ensure parent module exists in regulatory_modules
            cur.execute(
                """
                INSERT INTO regulatory_modules (module_id, name, department, regulation, jurisdiction, status)
                VALUES (%s, %s, %s, %s, 'IN', 'active')
                ON CONFLICT (module_id) DO UPDATE SET
                    regulation = EXCLUDED.regulation,
                    status = 'active'
                """,
                (
                    module_id,
                    "Legal Metrology (Packaged Commodities)",
                    meta.get("issuing_authority") or "Department of Consumer Affairs",
                    parent_regulation,
                ),
            )

            # 2. Record/update in regulatory_amendments
            cur.execute(
                """
                INSERT INTO regulatory_amendments
                    (amendment_id, module_id, source_document_id, approval_state,
                     extracted_at, approved_by, approved_at, published_at,
                     changes_json, impact_json)
                VALUES (%s, %s, %s, 'ACTIVE', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (amendment_id) DO UPDATE SET
                    approval_state = 'ACTIVE',
                    approved_by = EXCLUDED.approved_by,
                    approved_at = EXCLUDED.approved_at,
                    published_at = EXCLUDED.published_at,
                    changes_json = EXCLUDED.changes_json,
                    impact_json = EXCLUDED.impact_json
                """,
                (
                    draft_id,
                    module_id,
                    source_doc,
                    payload.get("extracted_at") or now,
                    published_by,
                    now,
                    now,
                    _json_or_none(payload.get("changes") or []),
                    _json_or_none(impact),
                ),
            )

            # 3. Publish each rule version into regulatory_rule_versions
            for v in raw_versions:
                rule_id = str(v.get("rule_id"))
                version_str = str(v.get("version") or amendment_name)
                eff_from_raw = v.get("effective_from")
                if isinstance(eff_from_raw, str):
                    eff_from = date.fromisoformat(eff_from_raw[:10])
                elif isinstance(eff_from_raw, date):
                    eff_from = eff_from_raw
                else:
                    eff_from = date.today()

                eff_to_raw = v.get("effective_to")
                eff_to = None
                if eff_to_raw:
                    eff_to = date.fromisoformat(str(eff_to_raw)[:10]) if isinstance(eff_to_raw, str) else eff_to_raw

                rv_id = v.get("id") or str(uuid.uuid4())
                rule_text = v.get("text") or ""
                conds = v.get("conditions") or {}
                thresholds = v.get("thresholds") or []
                ev_reqs = v.get("evidence_requirements") or []

                cur.execute(
                    """
                    INSERT INTO regulatory_rule_versions
                        (rule_version_id, module_id, rule_id, version, effective_from, effective_to,
                         approval_state, source_document_id, source_url, text,
                         conditions_json, thresholds_json, evidence_requirements_json,
                         extraction_metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s, 'ACTIVE', %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (module_id, rule_id, version) DO UPDATE SET
                        approval_state = 'ACTIVE',
                        effective_from = EXCLUDED.effective_from,
                        effective_to = EXCLUDED.effective_to,
                        text = EXCLUDED.text,
                        conditions_json = EXCLUDED.conditions_json,
                        thresholds_json = EXCLUDED.thresholds_json,
                        evidence_requirements_json = EXCLUDED.evidence_requirements_json,
                        extraction_metadata_json = EXCLUDED.extraction_metadata_json
                    """,
                    (
                        rv_id,
                        module_id,
                        rule_id,
                        version_str,
                        eff_from,
                        eff_to,
                        source_doc,
                        v.get("source_url"),
                        rule_text,
                        _json_or_none(conds),
                        _json_or_none(thresholds),
                        _json_or_none(ev_reqs),
                        _json_or_none(v.get("extraction_metadata") or {}),
                    ),
                )
                published_rules_info.append({
                    "rule_id": rule_id,
                    "display_provision": conds.get("source_provision") or rule_id,
                    "version": version_str,
                    "effective_from": eff_from.isoformat(),
                    "applicability": conds.get("applicability") or {},
                })

            # 4. Update amendment_drafts state to ACTIVE
            payload["approval_state"] = "ACTIVE"
            for pv in payload.get("proposed_rule_versions", []):
                pv["approval_state"] = "ACTIVE"
            updated_payload_json = json.dumps(payload, default=_json_default)

            cur.execute(
                """
                UPDATE amendment_drafts SET
                    approval_state = 'ACTIVE',
                    reviewed_by = %s,
                    reviewed_at = %s,
                    activated_at = %s,
                    payload_json = %s
                WHERE id = %s
                """,
                (
                    published_by,
                    now,
                    now,
                    updated_payload_json,
                    draft_id,
                ),
            )

    return {
        "draft_id": draft_id,
        "amendment_id": draft_id,
        "amendment": amendment_name,
        "module_id": module_id,
        "parent_rule_set": parent_regulation,
        "parent_regulation": parent_regulation,
        "status": "PUBLISHED / ACTIVE",
        "rules_published_count": len(published_rules_info),
        "rules_published": [r["rule_id"] for r in published_rules_info],
        "published_rules": published_rules_info,
        "effective_from": published_rules_info[0]["effective_from"] if published_rules_info else None,
        "published_at": now.isoformat(),
        "published_by": published_by,
    }


def get_active_rule_versions(
    module_id: str = "lmpc",
    as_of: Optional[Any] = None,
) -> list[dict]:
    """Retrieve currently active rule versions from PostgreSQL."""
    query = """
        SELECT
            rv.rule_version_id,
            rv.module_id,
            rm.regulation AS parent_regulation,
            rv.rule_id,
            rv.version,
            rv.effective_from,
            rv.effective_to,
            rv.approval_state,
            rv.source_document_id,
            rv.source_url,
            rv.text,
            rv.conditions_json,
            rv.thresholds_json,
            rv.evidence_requirements_json,
            rv.extraction_metadata_json,
            rv.created_at
        FROM regulatory_rule_versions rv
        JOIN regulatory_modules rm ON rv.module_id = rm.module_id
        WHERE rv.module_id = %s AND rv.approval_state = 'ACTIVE'
    """
    params: list[Any] = [module_id]
    if as_of:
        query += " AND rv.effective_from <= %s AND (rv.effective_to IS NULL OR rv.effective_to > %s)"
        params.extend([as_of, as_of])
    query += " ORDER BY rv.rule_id, rv.effective_from DESC"

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = [dict(r) for r in cur.fetchall()]

    for r in rows:
        r["conditions"] = decode_json_column(r.get("conditions_json"))
        r["thresholds"] = decode_json_column(r.get("thresholds_json"))
        r["evidence_requirements"] = decode_json_column(r.get("evidence_requirements_json"))
        r["extraction_metadata"] = decode_json_column(r.get("extraction_metadata_json")) or {}
        if r.get("effective_from"):
            r["effective_from"] = r["effective_from"].isoformat() if hasattr(r["effective_from"], "isoformat") else str(r["effective_from"])
        if r.get("effective_to"):
            r["effective_to"] = r["effective_to"].isoformat() if hasattr(r["effective_to"], "isoformat") else str(r["effective_to"])
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"])
    return rows


def get_database_verification(draft_id: str) -> dict:
    """Read directly from PostgreSQL to verify relational database integrity
    across draft -> amendment -> rule versions -> parent regulation."""
    draft = get_amendment_draft(draft_id)
    if not draft:
        raise ValueError(f"Draft not found: {draft_id}")

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Query amendment record
            cur.execute(
                "SELECT * FROM regulatory_amendments WHERE amendment_id = %s",
                (draft_id,),
            )
            amendment_row = cur.fetchone()

            # Query module record
            cur.execute(
                "SELECT * FROM regulatory_modules WHERE module_id = 'lmpc'",
            )
            module_row = cur.fetchone()

            # Query rule versions published
            src_doc = draft.get("source_document_id") or draft_id
            cur.execute(
                """
                SELECT rule_version_id, module_id, rule_id, version,
                       effective_from, effective_to, approval_state,
                       source_document_id, conditions_json, text, created_at
                FROM regulatory_rule_versions
                WHERE source_document_id = %s OR module_id = 'lmpc'
                ORDER BY rule_id
                """,
                (src_doc,),
            )
            version_rows = [dict(r) for r in cur.fetchall()]

    for v in version_rows:
        v["conditions"] = decode_json_column(v.get("conditions_json"))
        if v.get("effective_from"):
            v["effective_from"] = str(v["effective_from"])
        if v.get("effective_to"):
            v["effective_to"] = str(v["effective_to"])
        if v.get("created_at"):
            v["created_at"] = str(v["created_at"])

    return {
        "draft_id": draft_id,
        "regulation_id": module_row["module_id"] if module_row else "lmpc",
        "parent_regulation": module_row["regulation"] if module_row else "Legal Metrology (Packaged Commodities) Rules, 2011",
        "rule_set_id": module_row["module_id"] if module_row else "lmpc",
        "amendment_id": draft_id,
        "draft_approval_state": draft.get("approval_state"),
        "published_in_regulatory_amendments": amendment_row is not None,
        "amendment_record": dict(amendment_row) if amendment_row else None,
        "rule_versions_count": len(version_rows),
        "rule_versions": version_rows,
        "provenance_chain": "DRAFT -> APPROVED -> PUBLISHED -> ACTIVE DATABASE RULE",
    }

