"""Empty the local demo certificate store.

Run: .venv\\Scripts\\python -m trust.reset_demo_data

This removes certificate rows only. Recorded audits and their event streams in
``data/audits.db`` are left intact, so the reset never invents or edits evidence.
"""

from __future__ import annotations

import argparse

from config_loader import load_config, repo_path
from trust.certificate import clear_records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Delete every certificate while keeping the SQLite file."
    )
    parser.add_argument(
        "--db",
        help="certificate database path (default: certificate.db_path in config.yaml)",
    )
    args = parser.parse_args(argv)

    db_path = args.db or load_config()["certificate"]["db_path"]
    removed = clear_records(db_path)
    print(
        f"Cleared {removed} certificate record(s) from "
        f"{repo_path(db_path)}. The audit database was not touched."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
