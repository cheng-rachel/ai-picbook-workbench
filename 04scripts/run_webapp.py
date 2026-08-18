#!/usr/bin/env python3
"""Start the local teacher Demo Web App."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))

from backend.config import DATABASE_PATH  # noqa: E402
from webapp import create_server  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Power Up Picture Book Forge Web UI.")
    parser.add_argument("--db", default=str(DATABASE_PATH),
                        help="SQLite database path (default: structured reference DB)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    database_path = Path(args.db)
    if not database_path.exists():
        print(f"Database not found: {database_path}")
        return 1
    server = create_server(database_path, args.port)
    print(f"Power Up 绘编 running at http://127.0.0.1:{args.port}/ (db: {database_path})",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
