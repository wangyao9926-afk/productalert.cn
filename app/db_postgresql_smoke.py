from __future__ import annotations

from uuid import uuid4

from app.db import DB_BACKEND, apply_database_migrations, execute_sql, fetchone, get_db, insert_row


def require_postgresql() -> None:
    if DB_BACKEND.name != "postgresql":
        raise RuntimeError(
            "PostgreSQL smoke test requires DATABASE_URL to use postgresql://, "
            "postgres://, or postgresql+psycopg://."
        )


def run_smoke_test() -> dict:
    require_postgresql()

    marker = uuid4().hex
    email = f"smoke-{marker}@monitor.internal"
    site_url = f"https://smoke-{marker}.example"

    with get_db() as db:
        apply_database_migrations(db)
        user_id = insert_row(
            db,
            "users",
            {
                "email": email,
                "password_hash": "smoke-test",
            },
        )
        site_id = insert_row(
            db,
            "sites",
            {
                "user_id": user_id,
                "name": "PostgreSQL Smoke Site",
                "url": site_url,
                "scan_interval_minutes": 60,
            },
        )
        source_id = insert_row(
            db,
            "monitor_sources",
            {
                "site_id": site_id,
                "source_type": "homepage",
                "url": site_url,
                "scan_interval_minutes": 60,
            },
        )
        site = fetchone(
            db,
            """
            SELECT sites.id, sites.name, users.email
            FROM sites
            JOIN users ON users.id = sites.user_id
            WHERE sites.id = ?
            """,
            (site_id,),
        )
        if not site or site["email"] != email:
            raise RuntimeError("PostgreSQL smoke readback failed")

        execute_sql(db, "DELETE FROM monitor_sources WHERE id = ?", (source_id,))
        execute_sql(db, "DELETE FROM sites WHERE id = ?", (site_id,))
        execute_sql(db, "DELETE FROM users WHERE id = ?", (user_id,))

    return {
        "backend": DB_BACKEND.name,
        "user_id": user_id,
        "site_id": site_id,
        "source_id": source_id,
    }


def main() -> None:
    result = run_smoke_test()
    print(
        "postgresql smoke ok "
        f"user_id={result['user_id']} "
        f"site_id={result['site_id']} "
        f"source_id={result['source_id']}"
    )


if __name__ == "__main__":
    main()
