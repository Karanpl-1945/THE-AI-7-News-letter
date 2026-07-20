"""Create and verify PostgreSQL connections.

This module is only the shared connection boundary — schema creation lives in
`database/migrate.py` and LangGraph checkpointing lives in `database/checkpointer.py`.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Iterator

import psycopg
from dotenv import load_dotenv
from psycopg import Connection


DEFAULT_CONNECT_TIMEOUT_SECONDS = 10


class DatabaseConfigurationError(ValueError):
    """Raised when database environment settings are missing or invalid."""


def get_database_url() -> str:
    """Return the configured PostgreSQL URL without logging its credentials."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise DatabaseConfigurationError(
            "DATABASE_URL is not set. Add the PostgreSQL connection string to .env."
        )
    return database_url


def get_connect_timeout_seconds() -> int:
    """Return a positive connection timeout from the environment."""
    raw_value = os.getenv(
        "DATABASE_CONNECT_TIMEOUT_SECONDS",
        str(DEFAULT_CONNECT_TIMEOUT_SECONDS),
    )
    try:
        timeout = int(raw_value)
    except ValueError as exc:
        raise DatabaseConfigurationError(
            "DATABASE_CONNECT_TIMEOUT_SECONDS must be a positive integer."
        ) from exc

    if timeout <= 0:
        raise DatabaseConfigurationError(
            "DATABASE_CONNECT_TIMEOUT_SECONDS must be a positive integer."
        )
    return timeout


@contextmanager
def database_connection(database_url: str | None = None) -> Iterator[Connection]:
    """Open a transactional connection and always close it after use."""
    url = database_url or get_database_url()
    with psycopg.connect(
        url,
        connect_timeout=get_connect_timeout_seconds(),
        application_name="ai-newsletter",
    ) as connection:
        yield connection


def check_database_connection(database_url: str | None = None) -> None:
    """Run a minimal query, raising an exception if PostgreSQL is unavailable."""
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            if result != (1,):
                raise RuntimeError("PostgreSQL connection check returned an invalid result.")


def main() -> int:
    """CLI used to verify local or deployment database credentials."""
    load_dotenv()
    try:
        check_database_connection()
    except Exception as exc:
        print(f"[Database] Connection failed: {exc}")
        return 1

    print("[Database] PostgreSQL connection successful.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
