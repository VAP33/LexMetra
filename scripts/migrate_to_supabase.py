#!/usr/bin/env python3
"""
LexMetra - Supabase Database Migration & Synchronization Script
==============================================================
Applies the full LexMetra PostgreSQL schema and optionally copies local data
(users, products, inspections, canonical declarations, audit logs) to a remote
Supabase PostgreSQL database.

Usage:
  # 1. Apply schema and migrate data using environment variable:
  export SUPABASE_DB_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres?sslmode=require"
  python3 scripts/migrate_to_supabase.py

  # 2. Or pass database URL directly:
  python3 scripts/migrate_to_supabase.py --target-url="postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres?sslmode=require"

  # 3. Schema only (without copying local database rows):
  python3 scripts/migrate_to_supabase.py --schema-only
"""

import argparse
import os
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "backend" / "db" / "schema.sql"
DEFAULT_LOCAL_URL = os.environ.get(
    "LOCAL_DATABASE_URL",
    "postgresql://lmpc_app:lmpc_dev_pw@localhost:5433/lmpc"
)

TABLES_IN_ORDER = [
    "users",
    "products",
    "inspections",
    "inspection_facts",
    "inspection_findings",
    "inspection_sessions",
    "session_captures",
    "inspection_surfaces",
    "package_integrity_comparisons",
    "audit_log",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Migrate LexMetra schema and data to Supabase")
    parser.add_argument(
        "--target-url",
        default=os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL"),
        help="Supabase PostgreSQL connection string (supports direct or pooler URL with sslmode=require)",
    )
    parser.add_argument(
        "--source-url",
        default=DEFAULT_LOCAL_URL,
        help="Source local PostgreSQL connection string (defaults to port 5433 lmpc)",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Only create tables and indices, skip copying rows",
    )
    return parser.parse_args()


def apply_schema(target_conn):
    print(f"[*] Reading schema from {SCHEMA_FILE}...")
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"Schema file not found at {SCHEMA_FILE}")

    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with target_conn.cursor() as cur:
        print("[*] Applying schema to Supabase database...")
        cur.execute(sql)
    target_conn.commit()
    print("[+] Schema successfully created on Supabase.")


def copy_table_data(source_conn, target_conn, table_name):
    from psycopg2.extras import execute_batch, Json

    # Filter orphaned records that violate foreign keys from local dev experimentation
    query = f"SELECT * FROM {table_name}"
    if table_name in ("inspection_facts", "inspection_findings", "inspection_surfaces"):
        query = f"SELECT * FROM {table_name} WHERE inspection_id IN (SELECT inspection_id FROM inspections)"
    elif table_name == "session_captures":
        query = f"SELECT * FROM {table_name} WHERE session_id IN (SELECT session_id FROM inspection_sessions)"
    elif table_name == "package_integrity_comparisons":
        query = f"SELECT * FROM {table_name} WHERE inspection_id IN (SELECT inspection_id FROM inspections)"

    with source_conn.cursor(cursor_factory=RealDictCursor) as src_cur:
        try:
            src_cur.execute(query + ";")
            rows = src_cur.fetchall()
        except Exception as e:
            source_conn.rollback()
            print(f"[-] Could not read from source table {table_name}: {e}")
            return 0

    if not rows:
        print(f"  [i] Table '{table_name}' has 0 valid rows to transfer.")
        return 0

    # Read target table columns to only insert columns that exist on the target
    with target_conn.cursor() as tgt_cur:
        tgt_cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}';")
        target_cols = {r[0] for r in tgt_cur.fetchall()}

    valid_cols = [c for c in list(rows[0].keys()) if c in target_cols]
    if not valid_cols:
        return 0

    col_names = ", ".join(valid_cols)
    placeholders = ", ".join(["%s"] * len(valid_cols))

    insert_sql = f"""
        INSERT INTO {table_name} ({col_names})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING;
    """

    data = []
    for r in rows:
        row_vals = []
        for c in valid_cols:
            val = r[c]
            if isinstance(val, (dict, list)):
                row_vals.append(Json(val))
            else:
                row_vals.append(val)
        data.append(row_vals)

    try:
        with target_conn.cursor() as tgt_cur:
            execute_batch(tgt_cur, insert_sql, data, page_size=100)
        target_conn.commit()
        print(f"  [+] Transferred {len(data)} records into '{table_name}'.")
        return len(data)
    except Exception as e:
        target_conn.rollback()
        print(f"    [!] Error batch inserting into {table_name}: {e}")
        return 0


def verify_tables(target_conn):
    print("\n[*] Verifying tables on Supabase:")
    with target_conn.cursor() as cur:
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        tables = [r[0] for r in cur.fetchall()]
        for t in tables:
            cur.execute(f"SELECT count(*) FROM {t};")
            cnt = cur.fetchone()[0]
            print(f"  - public.{t:25} ({cnt} rows)")


def main():
    args = parse_args()

    if not args.target_url:
        print("[!] Error: No Supabase connection URL provided.")
        print("    Pass --target-url or set SUPABASE_DB_URL environment variable.")
        print("    Example:")
        print("    python3 scripts/migrate_to_supabase.py --target-url=\"postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres?sslmode=require\"")
        print("\n    To find your Supabase URL:")
        print("    1. Supabase Dashboard -> Project Settings -> Database -> Connection string (URI)")
        print("    2. Use Port 5432 (Direct) or Port 6543 (Session Pooler)")
        sys.exit(1)

    # Ensure sslmode=require for cloud Supabase connection
    target_url = args.target_url

    # Automatically fix passwords with unencoded '@' or special characters
    # e.g. postgresql://postgres:database2@lexmetra@db.ref.supabase.co:...
    if target_url.count("@") > 1 and "://" in target_url:
        import urllib.parse
        scheme, rest = target_url.split("://", 1)
        user_pass, host_part = rest.rsplit("@", 1)
        if ":" in user_pass:
            user, pwd = user_pass.split(":", 1)
            target_url = f"{scheme}://{user}:{urllib.parse.quote(pwd)}@{host_part}"

    if "supabase.co" in target_url and "sslmode" not in target_url:
        sep = "&" if "?" in target_url else "?"
        target_url = f"{target_url}{sep}sslmode=require"

    print(f"[*] Connecting to Supabase: {target_url.split('@')[-1]}")
    try:
        target_conn = psycopg2.connect(target_url, connect_timeout=10)
    except Exception as e:
        print(f"[!] Connection failed to Supabase: {e}")
        sys.exit(1)

    try:
        apply_schema(target_conn)

        if not args.schema_only:
            print(f"\n[*] Connecting to local database: {args.source_url}")
            try:
                source_conn = psycopg2.connect(args.source_url, connect_timeout=5)
                print("[*] Synchronizing existing data...")
                for tbl in TABLES_IN_ORDER:
                    copy_table_data(source_conn, target_conn, tbl)
                source_conn.close()
            except Exception as e:
                print(f"[!] Warning: Local database synchronization skipped ({e}). Schema was applied.")

        verify_tables(target_conn)
        print("\n[✓] Supabase database setup is 100% COMPLETE.")
        print("\nTo use this Supabase database on Render:")
        print(f"  Set environment variable in Render Dashboard or render.yaml:")
        print(f"  DATABASE_URL={target_url}")

    finally:
        target_conn.close()


if __name__ == "__main__":
    main()
