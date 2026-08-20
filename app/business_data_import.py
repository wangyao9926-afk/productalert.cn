from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from app.business_data_export import BUSINESS_TABLES


JSON_COLUMNS = {"notification_events", "field_confidence", "confidence_reasons", "features"}
SQLITE_STORAGE_COLUMNS = {
    "notification_events": "notification_events_json",
    "field_confidence": "field_confidence_json",
    "confidence_reasons": "confidence_reasons_json",
    "features": "features_json",
}


def _backend_name(target) -> str:
    return "postgresql" if target.__class__.__module__.startswith("psycopg") else "sqlite"


def _placeholder(backend: str) -> str:
    return "%s" if backend == "postgresql" else "?"


def database_row_id(row: object) -> int:
    """Return an inserted/fetched id from SQLite tuples or psycopg dict rows."""
    if isinstance(row, dict):
        return int(row["id"])
    return int(row[0])


def read_business_data_package(package_path: Path) -> dict:
    """Load the JSON baseline package produced by the safe exporter."""
    return json.loads(package_path.read_text(encoding="utf-8"))


def _storage_values(values: dict, backend: str) -> dict:
    stored: dict = {}
    for column, value in values.items():
        target_column = SQLITE_STORAGE_COLUMNS.get(column, column) if backend == "sqlite" else column
        if column in JSON_COLUMNS and value is not None:
            if backend == "postgresql":
                from psycopg.types.json import Jsonb

                value = Jsonb(value)
            else:
                value = json.dumps(value, ensure_ascii=False)
        stored[target_column] = value
    return stored


def _fetch_id(target, sql: str, params: Iterable[object]):
    row = target.execute(sql, tuple(params)).fetchone()
    return database_row_id(row) if row else None


def _insert(target, table: str, values: dict, backend: str) -> int:
    stored = _storage_values(values, backend)
    columns = list(stored)
    placeholder = _placeholder(backend)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholder for _ in columns)})"
    if backend == "postgresql":
        sql += " RETURNING id"
    cursor = target.execute(sql, tuple(stored[column] for column in columns))
    if backend == "postgresql":
        return database_row_id(cursor.fetchone())
    return int(cursor.lastrowid)


def _copy_values(row: dict, *omit: str) -> dict:
    return {key: value for key, value in row.items() if key not in {"id", *omit}}


def import_business_data(target, package: dict, target_user_id: int) -> dict[str, int]:
    """Import a safe baseline package and remap all records to a target owner.

    The function intentionally imports no credentials, sessions, webhook targets or
    notification rules. It is idempotent by each table's natural key.
    """
    if package.get("version") != 1:
        raise ValueError("Unsupported business data package version")
    tables = package.get("tables") or {}
    if any(table not in tables for table in BUSINESS_TABLES):
        raise ValueError("Business data package is missing required tables")

    backend = _backend_name(target)
    placeholder = _placeholder(backend)
    counts = {table: 0 for table in BUSINESS_TABLES}
    site_ids: dict[int, int] = {}
    source_ids: dict[int, int] = {}
    product_ids: dict[int, int] = {}

    try:
        for row in tables["sites"]:
            existing_id = _fetch_id(target, f"SELECT id FROM sites WHERE user_id = {placeholder} AND url = {placeholder}", (target_user_id, row["url"]))
            site_ids[row["id"]] = int(existing_id) if existing_id else _insert(target, "sites", {**_copy_values(row, "user_id"), "user_id": target_user_id}, backend)
            counts["sites"] += 1

        for row in tables["monitor_sources"]:
            target_site_id = site_ids[row["site_id"]]
            existing_id = _fetch_id(target, f"SELECT id FROM monitor_sources WHERE site_id = {placeholder} AND source_type = {placeholder} AND url = {placeholder}", (target_site_id, row["source_type"], row["url"]))
            source_ids[row["id"]] = int(existing_id) if existing_id else _insert(target, "monitor_sources", {**_copy_values(row, "site_id"), "site_id": target_site_id}, backend)
            counts["monitor_sources"] += 1

        for row in tables["known_urls"]:
            target_source_id = source_ids[row["source_id"]]
            existing_id = _fetch_id(target, f"SELECT id FROM known_urls WHERE source_id = {placeholder} AND url = {placeholder}", (target_source_id, row["url"]))
            if not existing_id:
                _insert(target, "known_urls", {**_copy_values(row, "source_id"), "source_id": target_source_id}, backend)
            counts["known_urls"] += 1

        for row in tables["products"]:
            target_site_id = site_ids[row["site_id"]]
            existing_id = _fetch_id(target, f"SELECT id FROM products WHERE site_id = {placeholder} AND url = {placeholder}", (target_site_id, row["url"]))
            source_id = row.get("source_id")
            product_values = {**_copy_values(row, "site_id", "source_id"), "site_id": target_site_id, "source_id": source_ids.get(source_id) if source_id else None}
            product_ids[row["id"]] = int(existing_id) if existing_id else _insert(target, "products", product_values, backend)
            counts["products"] += 1

        for row in tables["product_variants"]:
            target_product_id = product_ids[row["product_id"]]
            existing_id = _fetch_id(target, f"SELECT id FROM product_variants WHERE product_id = {placeholder} AND external_id = {placeholder}", (target_product_id, row["external_id"]))
            if not existing_id:
                _insert(target, "product_variants", {**_copy_values(row, "product_id"), "product_id": target_product_id}, backend)
            counts["product_variants"] += 1

        for row in tables["product_identifiers"]:
            target_product_id = product_ids[row["product_id"]]
            existing_id = _fetch_id(target, f"SELECT id FROM product_identifiers WHERE product_id = {placeholder} AND identifier_type = {placeholder} AND normalized_value = {placeholder}", (target_product_id, row["identifier_type"], row["normalized_value"]))
            if not existing_id:
                _insert(target, "product_identifiers", {**_copy_values(row, "product_id"), "product_id": target_product_id}, backend)
            counts["product_identifiers"] += 1

        target.commit()
    except Exception:
        target.rollback()
        raise
    return counts
