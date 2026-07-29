from __future__ import annotations

import unittest

from app.db_backends import postgresql_backend, sqlite_backend
from app.db import boolean_true_sql
from app.settings import ROOT


class DatabaseBooleanSqlTests(unittest.TestCase):
    def test_boolean_true_sql_uses_integer_for_sqlite(self) -> None:
        self.assertEqual(boolean_true_sql(sqlite_backend(ROOT), "enabled"), "enabled = 1")

    def test_boolean_true_sql_uses_boolean_literal_for_postgresql(self) -> None:
        self.assertEqual(boolean_true_sql(postgresql_backend(ROOT), "enabled"), "enabled IS TRUE")

    def test_boolean_true_sql_supports_qualified_columns(self) -> None:
        self.assertEqual(
            boolean_true_sql(postgresql_backend(ROOT), "monitor_sources.enabled"),
            "monitor_sources.enabled IS TRUE",
        )


if __name__ == "__main__":
    unittest.main()
