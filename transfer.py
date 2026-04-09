from __future__ import annotations

import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

SCRIPT_DIR = Path(__file__).resolve().parent
SQLITE_DB_PATH = SCRIPT_DIR / "breaker_instances.db"
SUPABASE_TABLE = "breaker_instances"
SIGNATURE_FIELDS = (
    "class",
    "model",
    "type",
    "pole",
    "min_current",
    "max_current",
    "height",
    "width",
    "depth",
)
FETCH_PAGE_SIZE = 1000
INSERT_BATCH_SIZE = 200


def build_supabase_client() -> Client:
    load_dotenv(SCRIPT_DIR / ".env")

    url = os.getenv("SUPABASE_URL") or ""
    key = os.getenv("SUPABASE_KEY") or ""
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY in .env")

    return create_client(url, key)


def fetch_sqlite_rows(db_path: Path) -> list[dict]:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")

    connection = sqlite3.connect(db_path, timeout=30.0)
    connection.row_factory = sqlite3.Row

    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (SUPABASE_TABLE,),
        )
        if cursor.fetchone() is None:
            raise RuntimeError(f"Table '{SUPABASE_TABLE}' was not found in {db_path.name}")

        cursor.execute(f"SELECT * FROM {SUPABASE_TABLE}")
        rows = cursor.fetchall()
    finally:
        connection.close()

    payloads = []
    for row in rows:
        row_dict = dict(row)
        payloads.append({field: row_dict.get(field) for field in SIGNATURE_FIELDS})

    return payloads


def fetch_existing_supabase_rows(client: Client) -> list[dict]:
    rows: list[dict] = []
    start = 0

    while True:
        response = (
            client.table(SUPABASE_TABLE)
            .select(",".join(SIGNATURE_FIELDS))
            .range(start, start + FETCH_PAGE_SIZE - 1)
            .execute()
        )
        batch = response.data or []
        rows.extend({field: item[field] if isinstance(item, dict) else getattr(item, field, None) for field in SIGNATURE_FIELDS} for item in batch)

        if len(batch) < FETCH_PAGE_SIZE:
            break

        start += FETCH_PAGE_SIZE

    return rows


def make_signature(row: dict) -> tuple:
    return tuple(row.get(field) for field in SIGNATURE_FIELDS)


def get_rows_to_insert(local_rows: list[dict], existing_rows: list[dict]) -> tuple[list[dict], int]:
    existing_counter = Counter(make_signature(row) for row in existing_rows)
    rows_to_insert: list[dict] = []
    skipped_rows = 0

    for row in local_rows:
        signature = make_signature(row)
        if existing_counter[signature] > 0:
            existing_counter[signature] -= 1
            skipped_rows += 1
            continue

        rows_to_insert.append(row)

    return rows_to_insert, skipped_rows


def insert_rows(client: Client, rows: list[dict]) -> int:
    inserted = 0

    for start in range(0, len(rows), INSERT_BATCH_SIZE):
        batch = rows[start:start + INSERT_BATCH_SIZE]
        client.table(SUPABASE_TABLE).insert(batch).execute()
        inserted += len(batch)

    return inserted


def main() -> int:
    try:
        client = build_supabase_client()
        local_rows = fetch_sqlite_rows(SQLITE_DB_PATH)
        existing_rows = fetch_existing_supabase_rows(client)
        rows_to_insert, skipped_rows = get_rows_to_insert(local_rows, existing_rows)

        if not local_rows:
            print("No rows found in breaker_instances.db. Nothing to transfer.")
            return 0

        if not rows_to_insert:
            print(
                "Transfer complete. SQLite rows already exist in Supabase.\n"
                f"Local rows checked: {len(local_rows)}\n"
                f"Rows already present: {skipped_rows}\n"
                "Rows inserted: 0"
            )
            return 0

        inserted_rows = insert_rows(client, rows_to_insert)
        print(
            "Transfer complete.\n"
            f"Local rows checked: {len(local_rows)}\n"
            f"Rows already present: {skipped_rows}\n"
            f"Rows inserted: {inserted_rows}"
        )
        return 0
    except Exception as exc:
        print(f"Transfer failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
