"""Apply the application's idempotent PostgreSQL schema."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from database.connection import database_connection


MIGRATIONS = (
    Path(__file__).with_name("migrations") / "001_summary_cache.sql",
    Path(__file__).with_name("migrations") / "002_workflow_tracking.sql",
)
APPLICATION_TABLES = (
    "source_items",
    "article_summaries",
    "newsletter_issues",
    "workflow_runs",
)


def apply_application_schema(database_url: str | None = None) -> None:
    """Apply all idempotent application schema files in order."""
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            for migration in MIGRATIONS:
                cursor.execute(migration.read_text(encoding="utf-8"))
            for table in APPLICATION_TABLES:
                cursor.execute("SELECT to_regclass(%s)", (table,))
                row = cursor.fetchone()
                if not row or row[0] is None:
                    raise RuntimeError(f"Expected PostgreSQL table was not created: {table}")


def main() -> int:
    load_dotenv()
    try:
        apply_application_schema()
    except Exception as exc:
        print(f"[Database] Application schema migration failed: {exc}")
        return 1

    print("[Database] Application schema is ready.")
    print(f"[Database] Managed tables: {', '.join(APPLICATION_TABLES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
