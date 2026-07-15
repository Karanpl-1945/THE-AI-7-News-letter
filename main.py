"""Entry point — run the newspaper once right now."""

import argparse
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from graph.pipeline import run_pipeline
from observability import flush_langfuse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the weekly AI newsletter.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate HTML and PDF without sending email.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Start a separate run instead of resuming/reusing this week's checkpoint.",
    )
    return parser.parse_args()


def validate_environment(dry_run: bool) -> None:
    required = [
        "GROQ_API_KEY",
        "DATABASE_URL",
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
    ]
    if not dry_run:
        required.extend(["EMAIL_SENDER", "EMAIL_PASSWORD"])

    missing = [key for key in required if not os.getenv(key)]
    if missing:
        print(f"[Error] Missing environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your values.")
        sys.exit(1)


if __name__ == "__main__":
    args = parse_args()
    validate_environment(args.dry_run)
    try:
        run_pipeline(dry_run=args.dry_run, force=args.force)
    finally:
        flush_langfuse()
