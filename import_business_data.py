from __future__ import annotations

import argparse
from pathlib import Path

from app.business_data_import import import_business_data, read_business_data_package
from app.db import get_db


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import a safe ProductAlert monitoring baseline into the configured database."
    )
    parser.add_argument("--package", type=Path, required=True, help="Path to the exported baseline JSON package")
    parser.add_argument(
        "--target-user-id",
        type=int,
        required=True,
        help="Existing target account ID that will own the imported monitored sites",
    )
    args = parser.parse_args()

    package = read_business_data_package(args.package)
    with get_db() as target:
        counts = import_business_data(target, package, args.target_user_id)
    print(f"Imported monitoring baseline: {counts}")


if __name__ == "__main__":
    main()
