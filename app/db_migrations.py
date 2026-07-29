from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from app.db_backends import DatabaseBackend


def migration_files(backend: DatabaseBackend) -> list[Path]:
    return sorted(backend.migration_dir.glob("*.sql"))


def ensure_schema_migrations_table(db: sqlite3.Connection, backend: DatabaseBackend) -> None:
    db.execute(
        backend.prepare_sql(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at {applied_at_type} NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """.format(applied_at_type=backend.schema_migrations_applied_at_type)
        )
    )


def migration_checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    single_quote = False
    double_quote = False
    line_comment = False
    block_comment = False
    dollar_quote: str | None = None
    index = 0

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if line_comment:
            current.append(char)
            if char == "\n":
                line_comment = False
            index += 1
            continue

        if block_comment:
            current.append(char)
            if char == "*" and next_char == "/":
                current.append(next_char)
                block_comment = False
                index += 2
            else:
                index += 1
            continue

        if dollar_quote:
            if sql.startswith(dollar_quote, index):
                current.append(dollar_quote)
                index += len(dollar_quote)
                dollar_quote = None
            else:
                current.append(char)
                index += 1
            continue

        if single_quote:
            current.append(char)
            if char == "'":
                if next_char == "'":
                    current.append(next_char)
                    index += 2
                    continue
                single_quote = False
            index += 1
            continue

        if double_quote:
            current.append(char)
            if char == '"':
                double_quote = False
            index += 1
            continue

        if char == "-" and next_char == "-":
            current.extend([char, next_char])
            line_comment = True
            index += 2
            continue

        if char == "/" and next_char == "*":
            current.extend([char, next_char])
            block_comment = True
            index += 2
            continue

        if char == "$":
            end = sql.find("$", index + 1)
            if end != -1:
                tag = sql[index : end + 1]
                tag_body = tag[1:-1]
                if tag_body == "" or tag_body.replace("_", "").isalnum():
                    current.append(tag)
                    dollar_quote = tag
                    index = end + 1
                    continue

        if char == "'":
            current.append(char)
            single_quote = True
            index += 1
            continue

        if char == '"':
            current.append(char)
            double_quote = True
            index += 1
            continue

        if char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            index += 1
            continue

        current.append(char)
        index += 1

    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def execute_migration_sql(db: sqlite3.Connection, sql: str, backend: DatabaseBackend) -> None:
    prepared_sql = backend.prepare_sql(sql)
    if backend.name == "sqlite":
        db.executescript(prepared_sql)
        return
    for statement in split_sql_statements(prepared_sql):
        db.execute(statement)


def apply_migrations(db: sqlite3.Connection, backend: DatabaseBackend) -> None:
    ensure_schema_migrations_table(db, backend)
    for migration_file in migration_files(backend):
        version = migration_file.name
        sql = migration_file.read_text(encoding="utf-8")
        checksum = migration_checksum(sql)
        applied = db.execute(
            backend.prepare_sql("SELECT checksum FROM schema_migrations WHERE version = ?"),
            (version,),
        ).fetchone()
        if applied:
            if applied["checksum"] != checksum:
                raise RuntimeError(f"Migration checksum mismatch: {version}")
            continue
        execute_migration_sql(db, sql, backend)
        db.execute(
            backend.prepare_sql("INSERT INTO schema_migrations (version, checksum) VALUES (?, ?)"),
            (version, checksum),
        )
