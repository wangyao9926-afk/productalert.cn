from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatabaseBackend:
    name: str
    migration_dir: Path
    placeholder: str
    schema_migrations_applied_at_type: str
    insert_ignore_prefix: str
    insert_ignore_suffix: str
    column_aliases: dict[str, str]
    json_columns: dict[str, str]

    def placeholders(self, count: int) -> str:
        if count < 1:
            raise ValueError("Placeholder count must be positive")
        return ", ".join(self.placeholder for _ in range(count))

    def insert_ignore_sql(self, table: str, columns_sql: str, placeholders_sql: str) -> str:
        return (
            f"{self.insert_ignore_prefix} {table} ({columns_sql}) "
            f"VALUES ({placeholders_sql}){self.insert_ignore_suffix}"
        )

    def prepare_sql(self, sql: str) -> str:
        if self.placeholder == "?":
            return sql
        return sql.replace("?", self.placeholder)

    def column_name(self, app_column: str) -> str:
        return self.column_aliases.get(app_column, app_column)

    def column_names(self, app_columns: list[str]) -> list[str]:
        return [self.column_name(column) for column in app_columns]


def sqlite_backend(root: Path) -> DatabaseBackend:
    return DatabaseBackend(
        name="sqlite",
        migration_dir=root / "app" / "migrations" / "sqlite",
        placeholder="?",
        schema_migrations_applied_at_type="TEXT",
        insert_ignore_prefix="INSERT OR IGNORE INTO",
        insert_ignore_suffix="",
        column_aliases={
            "notification_events": "notification_events_json",
            "field_confidence": "field_confidence_json",
            "confidence_reasons": "confidence_reasons_json",
            "features": "features_json",
            "result": "result_json",
            "diff": "diff_json",
            "payload": "payload_json",
            "metadata": "metadata_json",
            "event_types": "event_types_json",
        },
        json_columns={
            "notification_events_json": "notification_events",
            "field_confidence_json": "field_confidence",
            "confidence_reasons_json": "confidence_reasons",
            "features_json": "features",
            "result_json": "result",
            "diff_json": "diff",
            "payload_json": "payload",
            "metadata_json": "metadata",
            "event_types_json": "event_types",
        },
    )


def postgresql_backend(root: Path) -> DatabaseBackend:
    return DatabaseBackend(
        name="postgresql",
        migration_dir=root / "app" / "migrations" / "postgresql",
        placeholder="%s",
        schema_migrations_applied_at_type="TIMESTAMPTZ",
        insert_ignore_prefix="INSERT INTO",
        insert_ignore_suffix=" ON CONFLICT DO NOTHING",
        column_aliases={},
        json_columns={
            "notification_events": "notification_events",
            "field_confidence": "field_confidence",
            "confidence_reasons": "confidence_reasons",
            "features": "features",
            "result": "result",
            "diff": "diff",
            "payload": "payload",
            "metadata": "metadata",
            "event_types": "event_types",
        },
    )
