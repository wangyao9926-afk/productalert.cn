from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from app.db_backends import DatabaseBackend, postgresql_backend, sqlite_backend
from app.db_migrations import apply_migrations, migration_checksum, migration_files as backend_migration_files
from app.db_sqlite_maintenance import index_columns, run_sqlite_maintenance, table_columns
from app.settings import ROOT, DATA_DIR, DatabaseSettings, database_settings


RAW_DB_SETTINGS = database_settings()
AVAILABLE_BACKENDS: dict[str, DatabaseBackend] = {
    "sqlite": sqlite_backend(ROOT),
    "postgresql": postgresql_backend(ROOT),
}
DB_BACKEND = AVAILABLE_BACKENDS[RAW_DB_SETTINGS.backend]
DB_SETTINGS = RAW_DB_SETTINGS
DB_PATH = DB_SETTINGS.sqlite_path
SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def connect_sqlite(settings: DatabaseSettings) -> sqlite3.Connection:
    if settings.sqlite_path is None:
        raise RuntimeError("SQLite database path is not configured")
    settings.sqlite_path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def postgresql_url(settings: DatabaseSettings) -> str:
    return settings.url.replace("postgresql+psycopg://", "postgresql://", 1)


def connect_postgresql(settings: DatabaseSettings):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL DATABASE_URL requires psycopg. Install project requirements first."
        ) from exc

    return psycopg.connect(postgresql_url(settings), row_factory=dict_row)


def connect_database(settings: DatabaseSettings):
    if settings.backend == "sqlite":
        return connect_sqlite(settings)
    if settings.backend == "postgresql":
        return connect_postgresql(settings)
    raise RuntimeError(f"Unsupported database backend: {settings.backend}")


@contextmanager
def get_db() -> Iterator[Any]:
    conn = connect_database(DB_SETTINGS)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def last_insert_id(cursor) -> int:
    if DB_BACKEND.name == "postgresql":
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL insert did not return an id")
        if isinstance(row, dict):
            return int(row["id"])
        return int(row[0])
    return cursor.lastrowid


def is_integrity_error(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    try:
        import psycopg
    except ImportError:
        return False
    return isinstance(exc, psycopg.IntegrityError)


def validate_identifiers(*names: str) -> None:
    if any(not SQL_IDENTIFIER_RE.match(name) for name in names):
        raise ValueError("Invalid SQL identifier")


def placeholders(count: int) -> str:
    return DB_BACKEND.placeholders(count)


def column_list(columns: list[str]) -> str:
    validate_identifiers(*columns)
    return ", ".join(columns)


def storage_columns(columns: list[str]) -> list[str]:
    resolved = DB_BACKEND.column_names(columns)
    validate_identifiers(*resolved)
    return resolved


def storage_column(column: str) -> str:
    return storage_columns([column])[0]


def boolean_true_sql(backend: DatabaseBackend, column: str) -> str:
    parts = column.split(".")
    resolved_parts = [backend.column_name(part) for part in parts]
    validate_identifiers(*resolved_parts)
    resolved = ".".join(resolved_parts)
    if backend.name == "postgresql":
        return f"{resolved} IS TRUE"
    return f"{resolved} = 1"


def storage_values(values: dict) -> dict:
    return {DB_BACKEND.column_name(column): value for column, value in values.items()}


def json_dumps(value) -> Any:
    if DB_BACKEND.name == "postgresql":
        try:
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL JSON values require psycopg. Install project requirements first."
            ) from exc
        return Jsonb(value)
    return json.dumps(value, ensure_ascii=False)


def json_loads(value, default):
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def where_in_clause(column: str, values: list | tuple) -> tuple[str, list]:
    column = DB_BACKEND.column_name(column)
    validate_identifiers(column)
    if not values:
        raise ValueError("WHERE IN values must not be empty")
    return f"{column} IN ({placeholders(len(values))})", list(values)


def execute_sql(db: sqlite3.Connection, sql: str, params: list | tuple = ()):
    return db.execute(DB_BACKEND.prepare_sql(sql), params)


def fetchone(db: sqlite3.Connection, sql: str, params: list | tuple = ()):
    return execute_sql(db, sql, params).fetchone()


def fetchall(db: sqlite3.Connection, sql: str, params: list | tuple = ()):
    return execute_sql(db, sql, params).fetchall()


def insert_row(db: sqlite3.Connection, table: str, values: dict) -> int:
    if not values:
        raise ValueError("Insert values must not be empty")
    values = storage_values(values)
    validate_identifiers(table, *values.keys())
    columns = list(values.keys())
    sql = f"INSERT INTO {table} ({column_list(columns)}) VALUES ({placeholders(len(columns))})"
    if DB_BACKEND.name == "postgresql":
        sql = f"{sql} RETURNING id"
    cursor = execute_sql(db, sql, [values[column] for column in columns])
    return last_insert_id(cursor)


def insert_ignore(db: sqlite3.Connection, table: str, columns: list[str], values: tuple) -> None:
    columns = storage_columns(columns)
    validate_identifiers(table, *columns)
    execute_sql(
        db,
        DB_BACKEND.insert_ignore_sql(table, column_list(columns), placeholders(len(columns))),
        values,
    )


def assignment_list(columns: list[str]) -> str:
    columns = storage_columns(columns)
    validate_identifiers(*columns)
    return ", ".join(f"{column} = ?" for column in columns)


def update_by_id(db: sqlite3.Connection, table: str, row_id: int, updates: dict) -> None:
    if not updates:
        return
    validate_identifiers(table)
    updates = storage_values(updates)
    columns = list(updates.keys())
    clauses = assignment_list(columns)
    execute_sql(
        db,
        f"UPDATE {table} SET {clauses} WHERE id = ?",
        [updates[column] for column in columns] + [row_id],
    )


def update_by_id_when(db: sqlite3.Connection, table: str, row_id: int, updates: dict, conditions: dict) -> int:
    if not updates:
        return 0
    validate_identifiers(table)
    updates = storage_values(updates)
    conditions = storage_values(conditions)
    update_columns = list(updates.keys())
    condition_columns = list(conditions.keys())
    clauses = assignment_list(update_columns)
    validate_identifiers(*condition_columns)
    condition_sql = " AND ".join(f"{column} = ?" for column in condition_columns)
    cursor = execute_sql(
        db,
        f"UPDATE {table} SET {clauses} WHERE id = ? AND {condition_sql}",
        [updates[column] for column in update_columns]
        + [row_id]
        + [conditions[column] for column in condition_columns],
    )
    return cursor.rowcount


def select_by_id(db: sqlite3.Connection, table: str, row_id: int):
    validate_identifiers(table)
    return fetchone(db, f"SELECT * FROM {table} WHERE id = ?", (row_id,))


def migration_files(backend: DatabaseBackend | None = None) -> list:
    resolved = backend or DB_BACKEND
    return backend_migration_files(resolved)


def sqlite_migration_files() -> list:
    return migration_files(DB_BACKEND)


def apply_database_migrations(db: sqlite3.Connection) -> None:
    apply_migrations(db, DB_BACKEND)


def apply_sqlite_migrations(db: sqlite3.Connection) -> None:
    apply_database_migrations(db)


def init_db() -> None:
    with get_db() as db:
        apply_database_migrations(db)
        if DB_BACKEND.name == "sqlite":
            run_sqlite_maintenance(db)


def row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    defaults = {
        "notification_events": ["product_new"],
        "field_confidence": {},
        "confidence_reasons": [],
        "features": [],
        "result": {},
        "diff": [],
        "payload": {},
        "metadata": {},
    }
    for storage_column, app_column in DB_BACKEND.json_columns.items():
        if storage_column in data:
            data[app_column] = json_loads(data.pop(storage_column), defaults.get(app_column))
    # SQLite stores booleans as 0/1. Keep the public data contract consistent
    # with PostgreSQL and Pydantic by returning actual Python booleans.
    if "enabled" in data:
        data["enabled"] = bool(data["enabled"])
    return data
