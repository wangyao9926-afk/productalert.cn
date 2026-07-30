from __future__ import annotations

import sqlite3

from app.crawler import classify_product_url


def table_columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}


def index_columns(db: sqlite3.Connection, index_name: str) -> list[str]:
    return [row["name"] for row in db.execute(f"PRAGMA index_info({index_name})").fetchall()]


def ensure_column(db: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    if name not in table_columns(db, table):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def ensure_default_owner(db: sqlite3.Connection) -> None:
    db.execute(
        """
        INSERT OR IGNORE INTO users (id, email, password_hash, created_at)
        VALUES (1, 'local@monitor.internal', '', CURRENT_TIMESTAMP)
        """
    )


def ensure_user_url_index(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sites_user_url
        ON sites(user_id, url)
        """
    )


def has_global_site_url_unique(db: sqlite3.Connection) -> bool:
    for index in db.execute("PRAGMA index_list(sites)").fetchall():
        if not index["unique"]:
            continue
        columns = index_columns(db, index["name"])
        if columns == ["url"]:
            return True
    return False


def rebuild_sites_without_global_url_unique(db: sqlite3.Connection) -> None:
    if not has_global_site_url_unique(db):
        return
    db.execute("PRAGMA foreign_keys = OFF")
    db.executescript(
        """
        CREATE TABLE sites_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            scan_interval_minutes INTEGER NOT NULL DEFAULT 60,
            webhook_url TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            category TEXT,
            priority INTEGER NOT NULL DEFAULT 2,
            notes TEXT,
            notification_events_json TEXT NOT NULL DEFAULT '["product_new"]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_checked_at TEXT,
            last_status TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, url)
        );

        INSERT INTO sites_new (
            id, user_id, name, url, scan_interval_minutes, webhook_url, enabled,
            category, priority, notes, notification_events_json, created_at, last_checked_at, last_status
        )
        SELECT
            id, COALESCE(user_id, 1), name, url, scan_interval_minutes, webhook_url,
            enabled, category, priority, notes, COALESCE(notification_events_json, '["product_new"]'),
            created_at, last_checked_at, last_status
        FROM sites;

        DROP TABLE sites;
        ALTER TABLE sites_new RENAME TO sites;
        """
    )
    db.execute("PRAGMA foreign_keys = ON")


def migrate_existing_tables(db: sqlite3.Connection) -> None:
    ensure_default_owner(db)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            site_id INTEGER,
            name TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'webhook',
            target_url TEXT NOT NULL,
            event_types_json TEXT NOT NULL DEFAULT '["product_new"]',
            min_severity TEXT NOT NULL DEFAULT 'normal',
            inbox_status TEXT NOT NULL DEFAULT 'unread',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE
        )
        """
    )
    ensure_column(db, "sites", "user_id", "INTEGER")
    ensure_column(db, "sites", "category", "TEXT")
    ensure_column(db, "sites", "priority", "INTEGER NOT NULL DEFAULT 2")
    ensure_column(db, "sites", "notes", "TEXT")
    ensure_column(db, "sites", "notification_events_json", "TEXT NOT NULL DEFAULT '[\"product_new\"]'")
    ensure_column(db, "products", "source_id", "INTEGER")
    ensure_column(db, "products", "item_type", "TEXT NOT NULL DEFAULT 'unknown'")
    ensure_column(db, "products", "review_status", "TEXT NOT NULL DEFAULT 'unreviewed'")
    ensure_column(db, "products", "inbox_status", "TEXT NOT NULL DEFAULT 'unread'")
    ensure_column(db, "products", "discovery_status", "TEXT NOT NULL DEFAULT 'new'")
    ensure_column(db, "products", "extraction_source", "TEXT NOT NULL DEFAULT 'unknown'")
    ensure_column(db, "products", "confidence_score", "REAL NOT NULL DEFAULT 0")
    ensure_column(db, "products", "field_confidence_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(db, "products", "confidence_reasons_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(db, "products", "price_amount", "REAL")
    ensure_column(db, "products", "currency", "TEXT")
    ensure_column(db, "products", "compare_at_price", "REAL")
    ensure_column(db, "products", "availability", "TEXT")
    ensure_column(db, "products", "variant_count", "INTEGER")
    ensure_column(db, "change_events", "product_id", "INTEGER")
    ensure_column(db, "change_events", "assignee", "TEXT")
    ensure_column(db, "change_events", "review_note", "TEXT")
    ensure_column(db, "change_events", "false_positive_reason", "TEXT")
    ensure_column(db, "change_events", "reviewed_at", "TEXT")
    ensure_column(db, "notification_outbox", "event_id", "INTEGER")
    ensure_column(db, "notification_outbox", "event_type", "TEXT")
    ensure_column(db, "notification_rules", "event_types_json", "TEXT NOT NULL DEFAULT '[\"product_new\"]'")
    ensure_column(db, "notification_rules", "min_severity", "TEXT NOT NULL DEFAULT 'normal'")
    ensure_column(db, "notification_rules", "inbox_status", "TEXT NOT NULL DEFAULT 'unread'")
    ensure_column(db, "monitor_sources", "product_baseline_completed_at", "TEXT")
    ensure_column(db, "monitor_sources", "failure_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(db, "monitor_sources", "next_scan_after", "TEXT")
    ensure_column(db, "source_snapshots", "screenshot_hash", "TEXT")
    ensure_column(db, "source_snapshots", "screenshot_path", "TEXT")
    ensure_column(db, "source_snapshots", "visual_change_ratio", "REAL")
    ensure_column(db, "source_snapshots", "screenshot_error", "TEXT")
    db.execute("UPDATE sites SET user_id = 1 WHERE user_id IS NULL")
    rebuild_sites_without_global_url_unique(db)
    ensure_user_url_index(db)
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notification_rules_user_enabled
        ON notification_rules(user_id, enabled, created_at DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notification_rules_site
        ON notification_rules(site_id)
        """
    )
    if "notification_outbox" in {
        row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }:
        db.execute("UPDATE notification_outbox SET status = 'pending' WHERE status = 'sending'")
    db.execute("UPDATE sites SET notification_events_json = '[\"product_new\"]' WHERE notification_events_json IS NULL")


def migrate_product_classification(db: sqlite3.Connection) -> None:
    rows = db.execute(
        "SELECT id, url, item_type, review_status FROM products"
    ).fetchall()
    for row in rows:
        if row["review_status"] in {"confirmed", "false_positive"} and row["item_type"] != "unknown":
            continue
        item_type, review_status = classify_product_url(row["url"])
        db.execute(
            "UPDATE products SET item_type = ?, review_status = ? WHERE id = ?",
            (item_type, review_status, row["id"]),
        )


def migrate_default_sources(db: sqlite3.Connection) -> None:
    sites = db.execute("SELECT * FROM sites").fetchall()
    for site in sites:
        source = db.execute(
            "SELECT id FROM monitor_sources WHERE site_id = ? LIMIT 1",
            (site["id"],),
        ).fetchone()
        if source:
            continue
        db.execute(
            """
            INSERT INTO monitor_sources (
                site_id, source_type, url, scan_interval_minutes, enabled, last_status
            )
            VALUES (?, 'homepage', ?, ?, ?, ?)
            """,
            (
                site["id"],
                site["url"],
                site["scan_interval_minutes"],
                site["enabled"],
                "\u7b49\u5f85\u5efa\u7acb\u57fa\u7ebf",
            ),
        )


def run_sqlite_maintenance(db: sqlite3.Connection) -> None:
    migrate_existing_tables(db)
    migrate_product_classification(db)
    migrate_default_sources(db)
