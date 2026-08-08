"""Run the real API against a throwaway SQLite database, for end-to-end UI tests.

The E2E suite drives the actual browser against the actual backend — a UI test that talks
to a mock proves the mock works. What it must not require is the full Docker stack, or
developers will not run it.

PostgreSQL is still the deployment target; the models are plain SQLAlchemy, so the schema
is created here with ``metadata.create_all`` rather than through Alembic. Alembic remains
the only supported path for a real deployment — this script is for a disposable database
that is deleted after the run, and skipping migrations here means the E2E suite cannot be
used to claim the migrations work.

Usage::

    python scripts/serve_e2e.py --port 18010 --state-dir /tmp/indusopt-e2e
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def prepare(state_dir: Path, *, reset: bool) -> None:
    """Point the settings at a scratch directory and create the schema in it."""

    if reset and state_dir.exists():
        shutil.rmtree(state_dir)
    (state_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    os.environ["INDUSOPT_DATABASE_URL"] = f"sqlite+aiosqlite:///{state_dir / 'e2e.db'}"
    os.environ["INDUSOPT_ARTIFACT_ROOT"] = str(state_dir / "artifacts")
    os.environ.setdefault("INDUSOPT_LLM_PROVIDER", "none")

    from app.core.db import get_engine
    from app.models import Base

    async def create() -> None:
        async with get_engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await get_engine().dispose()

    asyncio.run(create())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18010)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("/tmp/indusopt-e2e"),
        help="Scratch directory for the SQLite file and generated artifacts.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Reuse an existing state directory instead of wiping it first.",
    )
    arguments = parser.parse_args()

    prepare(arguments.state_dir, reset=not arguments.keep)

    import uvicorn
    from app.main import create_app

    uvicorn.run(create_app(), host=arguments.host, port=arguments.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
