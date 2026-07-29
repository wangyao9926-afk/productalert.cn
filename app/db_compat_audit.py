from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.settings import ROOT


APP_DIR = ROOT / "app"
ALLOWED_SQLITE_FILES = {
    "db.py",
    "db_backends.py",
    "db_migrations.py",
    "db_sqlite_maintenance.py",
    "db_compat_audit.py",
}
ALLOWED_JSON_STORAGE_FILES = {
    "db_backends.py",
    "db_sqlite_maintenance.py",
    "db_compat_audit.py",
}
DATABASE_WRITE_MODULES = {
    "main.py",
    "monitor.py",
    "notifier.py",
    "task_queue.py",
    "auth.py",
}
SQLITE_JSON_COLUMN_RE = re.compile(r"\b[a-zA-Z_]+_json\b")


@dataclass(frozen=True)
class Finding:
    category: str
    severity: str
    path: Path
    line: int
    text: str


def iter_python_lines() -> list[tuple[Path, int, str]]:
    rows: list[tuple[Path, int, str]] = []
    for path in sorted(APP_DIR.glob("*.py")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            rows.append((path, line_number, line))
    return rows


def audit_sqlite_specific_runtime(lines: list[tuple[Path, int, str]]) -> list[Finding]:
    findings: list[Finding] = []
    for path, line_number, line in lines:
        if path.name in ALLOWED_SQLITE_FILES:
            continue
        stripped = line.strip()
        if stripped.startswith("import sqlite3") or stripped.startswith("from sqlite3 import"):
            findings.append(
                Finding(
                    category="sqlite-runtime-import",
                    severity="high",
                    path=path,
                    line=line_number,
                    text=stripped,
                )
            )
        if "sqlite3." in stripped:
            findings.append(
                Finding(
                    category="sqlite-runtime-reference",
                    severity="high",
                    path=path,
                    line=line_number,
                    text=stripped,
                )
            )
    return findings


def audit_sqlite_only_sql(lines: list[tuple[Path, int, str]]) -> list[Finding]:
    findings: list[Finding] = []
    sqlite_tokens = [
        "PRAGMA ",
        "AUTOINCREMENT",
        "INSERT OR IGNORE",
        "sqlite_master",
        "executescript(",
        "lastrowid",
    ]
    for path, line_number, line in lines:
        if path.name in ALLOWED_SQLITE_FILES:
            continue
        stripped = line.strip()
        for token in sqlite_tokens:
            if token in stripped:
                findings.append(
                    Finding(
                        category="sqlite-only-sql",
                        severity="medium",
                        path=path,
                        line=line_number,
                        text=stripped,
                    )
                )
    return findings


def audit_json_storage_names(lines: list[tuple[Path, int, str]]) -> list[Finding]:
    findings: list[Finding] = []
    for path, line_number, line in lines:
        if path.name in ALLOWED_JSON_STORAGE_FILES:
            continue
        stripped = line.strip()
        if SQLITE_JSON_COLUMN_RE.search(stripped):
            findings.append(
                Finding(
                    category="sqlite-json-column-name",
                    severity="medium",
                    path=path,
                    line=line_number,
                    text=stripped,
                )
            )
    return findings


def audit_raw_json_parameter_adaptation(lines: list[tuple[Path, int, str]]) -> list[Finding]:
    findings: list[Finding] = []
    for path, line_number, line in lines:
        if path.name not in DATABASE_WRITE_MODULES:
            continue
        if path.name in {"db.py", "db_backends.py", "db_compat_audit.py"}:
            continue
        stripped = line.strip()
        if "json.dumps(" in stripped:
            findings.append(
                Finding(
                    category="raw-json-parameter-adaptation",
                    severity="medium",
                    path=path,
                    line=line_number,
                    text=stripped,
                )
            )
    return findings


def run_audit() -> list[Finding]:
    lines = iter_python_lines()
    findings: list[Finding] = []
    findings.extend(audit_sqlite_specific_runtime(lines))
    findings.extend(audit_sqlite_only_sql(lines))
    findings.extend(audit_json_storage_names(lines))
    findings.extend(audit_raw_json_parameter_adaptation(lines))
    return findings


def main() -> None:
    findings = run_audit()
    if not findings:
        print("database compatibility audit ok")
        return

    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        grouped.setdefault(finding.category, []).append(finding)

    for category, category_findings in grouped.items():
        print(f"{category}: {len(category_findings)}")
        for finding in category_findings:
            relative_path = finding.path.relative_to(ROOT)
            print(f"  [{finding.severity}] {relative_path}:{finding.line} {finding.text}")


if __name__ == "__main__":
    main()
