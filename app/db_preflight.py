from __future__ import annotations

from dataclasses import dataclass

from app.db_backends import DatabaseBackend, postgresql_backend, sqlite_backend
from app.db_migrations import migration_checksum, migration_files, split_sql_statements
from app.settings import ROOT


@dataclass(frozen=True)
class MigrationCheck:
    backend: str
    version: str
    checksum: str
    statement_count: int


def available_backends() -> list[DatabaseBackend]:
    return [
        sqlite_backend(ROOT),
        postgresql_backend(ROOT),
    ]


def check_backend_migrations(backend: DatabaseBackend) -> list[MigrationCheck]:
    files = migration_files(backend)
    if not files:
        raise RuntimeError(f"No migration files found for backend: {backend.name}")

    checks: list[MigrationCheck] = []
    for migration_file in files:
        sql = migration_file.read_text(encoding="utf-8")
        checksum = migration_checksum(sql)
        statements = split_sql_statements(sql)
        if not statements:
            raise RuntimeError(f"Migration file is empty: {migration_file}")
        checks.append(
            MigrationCheck(
                backend=backend.name,
                version=migration_file.name,
                checksum=checksum,
                statement_count=len(statements),
            )
        )
    return checks


def run_preflight() -> list[MigrationCheck]:
    checks: list[MigrationCheck] = []
    for backend in available_backends():
        checks.extend(check_backend_migrations(backend))
    return checks


def main() -> None:
    for check in run_preflight():
        print(
            f"{check.backend} {check.version} "
            f"statements={check.statement_count} checksum={check.checksum}"
        )


if __name__ == "__main__":
    main()
