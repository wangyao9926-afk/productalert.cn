from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from json import dumps
from json import loads as json_loads
from pathlib import Path


BUSINESS_TABLES = (
    "sites",
    "monitor_sources",
    "known_urls",
    "products",
    "product_variants",
    "product_identifiers",
)
JSON_STORAGE_COLUMNS = {
    "notification_events_json": "notification_events",
    "field_confidence_json": "field_confidence",
    "confidence_reasons_json": "confidence_reasons",
    "features_json": "features",
}


def _table_exists(db: sqlite3.Connection, table: str) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
    )


def _rows(db: sqlite3.Connection, sql: str, params: Iterable[object] = ()) -> list[dict]:
    rows = []
    for row in db.execute(sql, tuple(params)).fetchall():
        data = dict(row)
        for storage_column, logical_column in JSON_STORAGE_COLUMNS.items():
            if storage_column in data:
                raw_value = data.pop(storage_column)
                data[logical_column] = json_loads(raw_value) if raw_value else None
        rows.append(data)
    return rows


def _empty_package() -> dict:
    return {
        "version": 1,
        "tables": {table: [] for table in BUSINESS_TABLES},
        "counts": {table: 0 for table in BUSINESS_TABLES},
    }


def export_business_data(source: sqlite3.Connection, user_id: int) -> dict:
    """Export only baseline records required to resume monitoring in a new database.

    Authentication material, session tokens, notification rules and webhook URLs are
    intentionally not included. They must be configured again in the target runtime.
    """
    package = _empty_package()
    if not _table_exists(source, "sites"):
        return package

    sites = _rows(
        source,
        "SELECT id, user_id, name, url, scan_interval_minutes, enabled, category, priority, notes, notification_events_json, created_at, last_checked_at, last_status FROM sites WHERE user_id = ? ORDER BY id",
        (user_id,),
    )
    package["tables"]["sites"] = sites
    site_ids = [row["id"] for row in sites]
    if not site_ids:
        package["counts"] = {table: 0 for table in BUSINESS_TABLES}
        return package

    site_placeholders = ", ".join("?" for _ in site_ids)
    if _table_exists(source, "monitor_sources"):
        sources = _rows(
            source,
            f"SELECT * FROM monitor_sources WHERE site_id IN ({site_placeholders}) ORDER BY id",
            site_ids,
        )
        package["tables"]["monitor_sources"] = sources
    else:
        sources = []
    source_ids = [row["id"] for row in sources]

    if source_ids and _table_exists(source, "known_urls"):
        source_placeholders = ", ".join("?" for _ in source_ids)
        package["tables"]["known_urls"] = _rows(
            source,
            f"SELECT * FROM known_urls WHERE source_id IN ({source_placeholders}) ORDER BY id",
            source_ids,
        )

    if _table_exists(source, "products"):
        products = _rows(
            source,
            f"SELECT * FROM products WHERE site_id IN ({site_placeholders}) ORDER BY id",
            site_ids,
        )
        package["tables"]["products"] = products
    else:
        products = []
    product_ids = [row["id"] for row in products]

    if product_ids:
        product_placeholders = ", ".join("?" for _ in product_ids)
        for table in ("product_variants", "product_identifiers"):
            if _table_exists(source, table):
                package["tables"][table] = _rows(
                    source,
                    f"SELECT * FROM {table} WHERE product_id IN ({product_placeholders}) ORDER BY id",
                    product_ids,
                )

    package["counts"] = {table: len(rows) for table, rows in package["tables"].items()}
    return package


def write_business_data_export(source: sqlite3.Connection, user_id: int, output_path: Path) -> Path:
    package = export_business_data(source, user_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path
