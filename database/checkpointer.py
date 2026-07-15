"""Initialize LangGraph's PostgreSQL checkpoint storage.

The newsletter pipeline is not connected to this checkpointer yet. Running this
module only applies LangGraph's own idempotent checkpoint-table migrations.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver

from database.connection import get_database_url


LANGGRAPH_CHECKPOINT_TABLES = (
    "checkpoint_migrations",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
)


@contextmanager
def postgres_checkpointer(
    database_url: str | None = None,
) -> Iterator[PostgresSaver]:
    """Yield a PostgresSaver whose connection is closed after use."""
    url = database_url or get_database_url()
    with PostgresSaver.from_conn_string(url) as checkpointer:
        yield checkpointer


def initialize_checkpoint_storage(database_url: str | None = None) -> None:
    """Create or migrate LangGraph's checkpoint tables safely."""
    with postgres_checkpointer(database_url) as checkpointer:
        checkpointer.setup()


def main() -> int:
    """Initialize checkpoint storage from the DATABASE_URL in .env."""
    load_dotenv()
    try:
        initialize_checkpoint_storage()
    except Exception as exc:
        print(f"[Checkpoint] Initialization failed: {exc}")
        return 1

    print("[Checkpoint] LangGraph PostgreSQL storage is ready.")
    print(f"[Checkpoint] Managed tables: {', '.join(LANGGRAPH_CHECKPOINT_TABLES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
