from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from app.business_data_export import write_business_data_export


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ProductAlert monitoring baselines without credentials or webhook targets.")
    parser.add_argument("--source-db", type=Path, required=True, help="Path to the SQLite monitor database")
    parser.add_argument("--user-id", type=int, required=True, help="Owner ID whose monitored sites will be exported")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON package path")
    args = parser.parse_args()

    source = sqlite3.connect(args.source_db)
    source.row_factory = sqlite3.Row
    try:
        output = write_business_data_export(source, args.user_id, args.output)
        print(f"Exported monitoring baseline to {output}")
    finally:
        source.close()


if __name__ == "__main__":
    main()
