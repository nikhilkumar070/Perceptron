#!/usr/bin/env python3
"""
Preceptron SQLite to Neon PostgreSQL Data Migration Tool
=========================================================
Migrates all data from the local Preceptron SQLite database to Neon PostgreSQL.

Usage:
    # Dry run (inspect and report only, makes zero changes to Neon):
    python backend/migrate_sqlite_to_neon.py --dry-run

    # Perform the actual migration:
    python backend/migrate_sqlite_to_neon.py
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, List, Tuple

BACKEND_DIR = Path(__file__).resolve().parent
BASE_DIR = BACKEND_DIR.parent
DEFAULT_SQLITE_PATH = BASE_DIR / "data" / "preceptron.db"
FALLBACK_SQLITE_PATH = BACKEND_DIR / "data" / "preceptron.db"

# Exact PostgreSQL DDL schemas matching backend/main.py
SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS users(
        id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL, role TEXT NOT NULL, profile_complete INTEGER DEFAULT 1,
        college TEXT DEFAULT '', branch TEXT DEFAULT 'CSE', graduation_year INTEGER DEFAULT 2027,
        target_role TEXT DEFAULT 'Software Engineer'
    )""",
    """CREATE TABLE IF NOT EXISTS sessions(
        token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS tasks(
        id TEXT PRIMARY KEY, title TEXT, category TEXT, difficulty TEXT,
        estimated_minutes INTEGER, status TEXT, date TEXT, details TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS resume_analyses(
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, filename TEXT, role TEXT, score INTEGER,
        payload TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS assessment_attempts(
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, question_id TEXT NOT NULL, selected_index INTEGER,
        correct INTEGER NOT NULL, category TEXT NOT NULL, topic TEXT NOT NULL, difficulty TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS practice_attempts(
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, question_id TEXT NOT NULL, selected_index INTEGER,
        correct INTEGER NOT NULL, category TEXT NOT NULL, topic TEXT NOT NULL, difficulty TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
]

TABLE_ORDER = [
    "users",
    "sessions",
    "tasks",
    "resume_analyses",
    "assessment_attempts",
    "practice_attempts",
]

# Primary keys for ON CONFLICT DO NOTHING
TABLE_PKS = {
    "users": ["id"],
    "sessions": ["token"],
    "tasks": ["id"],
    "resume_analyses": ["id"],
    "assessment_attempts": ["id"],
    "practice_attempts": ["id"],
}


def mask_database_url(url: str) -> str:
    """Safely mask password in database connection string for logging."""
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", url)


def locate_sqlite_db() -> Path:
    """Locate the actual SQLite database file used by the Preceptron application."""
    if DEFAULT_SQLITE_PATH.exists():
        return DEFAULT_SQLITE_PATH
    if FALLBACK_SQLITE_PATH.exists():
        return FALLBACK_SQLITE_PATH
    # If neither exists, check if user provided custom path
    return DEFAULT_SQLITE_PATH


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate Preceptron SQLite database to Neon PostgreSQL."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without modifying Neon PostgreSQL.",
    )
    parser.add_argument(
        "--sqlite-path",
        type=str,
        default="",
        help="Optional custom path to preceptron.db SQLite database file.",
    )
    args = parser.parse_args()

    print("==================================================")
    print("Preceptron SQLite -> Neon PostgreSQL Migration")
    print("==================================================")

    # 1. Check DATABASE_URL
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("\nERROR: DATABASE_URL environment variable is missing.", file=sys.stderr)
        print("Please set DATABASE_URL with your Neon PostgreSQL connection string.", file=sys.stderr)
        print("Example:", file=sys.stderr)
        print('  export DATABASE_URL="postgresql://user:pass@ep-xyz.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"', file=sys.stderr)
        print("  python backend/migrate_sqlite_to_neon.py", file=sys.stderr)
        sys.exit(1)

    masked_url = mask_database_url(database_url)
    print(f"\nTarget Neon Database: {masked_url}")

    # 2. Check SQLite path
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else locate_sqlite_db()
    if not sqlite_path.exists():
        print(f"\nERROR: SQLite database file not found at: {sqlite_path}", file=sys.stderr)
        sys.exit(1)

    print(f"SQLite database: {sqlite_path}")

    # 3. Read SQLite tables and counts
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    existing_sqlite_tables = [
        r[0]
        for r in sqlite_cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    print(f"Tables found in SQLite: {', '.join(existing_sqlite_tables)}")

    sqlite_counts = {}
    sqlite_data = {}
    for table in TABLE_ORDER:
        if table in existing_sqlite_tables:
            rows = sqlite_cur.execute(f"SELECT * FROM {table}").fetchall()
            sqlite_counts[table] = len(rows)
            sqlite_data[table] = rows
            print(f"  {table}: {len(rows)} rows")
        else:
            sqlite_counts[table] = 0
            sqlite_data[table] = []
            print(f"  {table}: 0 rows (table not present in SQLite)")

    if args.dry_run:
        print("\n[DRY RUN MODE] The following would be performed:")
        print("  1. Connect to Neon PostgreSQL and verify connectivity.")
        print("  2. Ensure all 6 target tables exist (DDL CREATE TABLE IF NOT EXISTS).")
        for table in TABLE_ORDER:
            print(f"  3. Insert/sync {sqlite_counts[table]} rows into '{table}' (ON CONFLICT DO NOTHING).")
        print("  4. Check and synchronize PostgreSQL sequences for any SERIAL/auto-increment columns.")
        print("\nDry run completed successfully. No changes were made to Neon PostgreSQL.")
        sqlite_conn.close()
        return

    # 4. Connect to Neon PostgreSQL using psycopg
    print("\nConnecting to Neon...")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        print("ERROR: 'psycopg' library is required. Install via: pip install 'psycopg[binary,pool]>=3.2'", file=sys.stderr)
        sqlite_conn.close()
        sys.exit(1)

    try:
        pg_conn = psycopg.connect(database_url, autocommit=False)
    except Exception as exc:
        print(f"ERROR: Could not connect to Neon PostgreSQL: {exc}", file=sys.stderr)
        sqlite_conn.close()
        sys.exit(1)

    print("Connected to Neon PostgreSQL successfully.")

    try:
        with pg_conn.cursor() as pg_cur:
            # 5. Create tables if not exist
            print("\nEnsuring PostgreSQL schema...")
            for stmt in SCHEMA_STATEMENTS:
                pg_cur.execute(stmt)
            pg_conn.commit()
            print("Schema verification complete.")

            # 6. Copy rows table by table
            print("\nMigrating rows to Neon PostgreSQL...")
            total_migrated = 0

            for table in TABLE_ORDER:
                rows = sqlite_data[table]
                if not rows:
                    print(f"  {table}: 0 rows to copy.")
                    continue

                # Get columns from SQLite cursor
                col_names = [col[0] for col in sqlite_cur.execute(f"SELECT * FROM {table} LIMIT 1").description]
                cols_str = ", ".join(col_names)
                placeholders = ", ".join(["%s"] * len(col_names))
                pk_cols = TABLE_PKS.get(table, ["id"])
                conflict_target = ", ".join(pk_cols)

                insert_sql = (
                    f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) "
                    f"ON CONFLICT ({conflict_target}) DO NOTHING"
                )

                # Prepare row values
                row_values = []
                for row in rows:
                    row_values.append(tuple(row[col] for col in col_names))

                # Count rows before
                pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
                count_before = pg_cur.fetchone()[0]

                pg_cur.executemany(insert_sql, row_values)
                pg_conn.commit()

                # Count rows after
                pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
                count_after = pg_cur.fetchone()[0]
                newly_inserted = count_after - count_before

                print(f"  {table}: {len(rows)} local rows processed -> {newly_inserted} newly inserted (total in Neon: {count_after})")
                total_migrated += newly_inserted

            # 7. Check sequences (if any sequence exists in public schema)
            print("\nChecking PostgreSQL sequences...")
            pg_cur.execute("""
                SELECT sequence_name FROM information_schema.sequences
                WHERE sequence_schema = 'public'
            """)
            sequences = pg_cur.fetchall()
            if sequences:
                for seq_row in sequences:
                    seq_name = seq_row[0]
                    print(f"  Found sequence: {seq_name}")
            else:
                print("  No sequences found (all table IDs are TEXT/UUID).")

        pg_conn.close()
        sqlite_conn.close()

        print("\n==================================================")
        print("Migration completed successfully.")
        print(f"Total new rows written to Neon: {total_migrated}")
        print("==================================================")

    except Exception as exc:
        pg_conn.rollback()
        pg_conn.close()
        sqlite_conn.close()
        print(f"\nERROR during migration: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

