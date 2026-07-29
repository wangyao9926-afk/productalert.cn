from __future__ import annotations

from app.db import DB_BACKEND, fetchone, get_db


def check_database() -> dict:
    with get_db() as db:
        row = fetchone(db, "SELECT 1 AS ok")
    value = row["ok"] if isinstance(row, dict) else row[0]
    if int(value) != 1:
        raise RuntimeError("database SELECT 1 returned an unexpected value")
    return {"backend": DB_BACKEND.name}


def main() -> None:
    result = check_database()
    print(f"database health ok backend={result['backend']}")


if __name__ == "__main__":
    main()
