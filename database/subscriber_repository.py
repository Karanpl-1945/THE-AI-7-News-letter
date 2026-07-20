"""Persistence operations for the admin-managed subscriber list."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from uuid import UUID, uuid4

from dotenv import load_dotenv

from database.connection import database_connection


@dataclass(frozen=True)
class SubscriberRecord:
    id: UUID
    email: str
    status: str


def add_subscriber(email: str, *, database_url: str | None = None) -> SubscriberRecord:
    """Insert a subscriber, or reactivate one that previously unsubscribed."""
    subscriber_id = uuid4()
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO subscribers (id, email, status)
                VALUES (%s, %s, 'active')
                ON CONFLICT (email) DO UPDATE SET
                    status = 'active',
                    updated_at = NOW()
                RETURNING id, email, status
                """,
                (subscriber_id, email.strip().lower()),
            )
            row = cursor.fetchone()

    if not row:
        raise RuntimeError("PostgreSQL did not return a subscriber record.")
    return SubscriberRecord(id=row[0], email=row[1], status=row[2])


def remove_subscriber(email: str, *, database_url: str | None = None) -> None:
    """Mark a subscriber unsubscribed without deleting their history."""
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE subscribers
                SET status = 'unsubscribed', updated_at = NOW()
                WHERE email = %s
                """,
                (email.strip().lower(),),
            )


def list_active_subscribers(*, database_url: str | None = None) -> list[SubscriberRecord]:
    """Return every subscriber currently eligible to receive an issue."""
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, status
                FROM subscribers
                WHERE status = 'active'
                ORDER BY created_at
                """,
            )
            rows = cursor.fetchall()

    return [SubscriberRecord(id=row[0], email=row[1], status=row[2]) for row in rows]


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Manage the newsletter subscriber list.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add or reactivate a subscriber.")
    add_parser.add_argument("email")

    remove_parser = subparsers.add_parser("remove", help="Unsubscribe an email address.")
    remove_parser.add_argument("email")

    subparsers.add_parser("list", help="List active subscribers.")

    args = parser.parse_args()

    try:
        if args.command == "add":
            record = add_subscriber(args.email)
            print(f"[Subscribers] Active: {record.email}")
        elif args.command == "remove":
            remove_subscriber(args.email)
            print(f"[Subscribers] Unsubscribed: {args.email}")
        else:
            for record in list_active_subscribers():
                print(record.email)
    except Exception as exc:
        print(f"[Subscribers] Failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
