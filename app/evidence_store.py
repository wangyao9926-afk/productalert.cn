from __future__ import annotations

from pathlib import Path

from app.settings import DATA_DIR


EVIDENCE_DIR = DATA_DIR / "evidence"


def evidence_path(relative_path: str) -> Path:
    root = EVIDENCE_DIR.resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Evidence path escapes the private evidence directory")
    return target


def save_screenshot(source_id: int, snapshot_id: int, png: bytes) -> str:
    relative_path = Path(f"source-{source_id}") / f"snapshot-{snapshot_id}.png"
    target = evidence_path(relative_path.as_posix())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)
    return relative_path.as_posix()


def load_screenshot(relative_path: str) -> bytes | None:
    target = evidence_path(relative_path)
    return target.read_bytes() if target.is_file() else None
