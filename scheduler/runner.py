"""APScheduler-based weekly automation. Run this once and leave it running."""

import os
from dotenv import load_dotenv
load_dotenv()

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger


def run_newspaper():
    from graph.pipeline import run_pipeline
    from observability import flush_langfuse
    try:
        run_pipeline()
    finally:
        flush_langfuse()


def start_scheduler():
    day    = os.getenv("SCHEDULE_DAY",    "sunday")
    hour   = int(os.getenv("SCHEDULE_HOUR",   "8"))
    minute = int(os.getenv("SCHEDULE_MINUTE", "0"))

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        run_newspaper,
        trigger=CronTrigger(day_of_week=day[:3], hour=hour, minute=minute),
        id="ai_newspaper",
        name="AI Dispatch Weekly",
        replace_existing=True,
    )

    print(f"[Scheduler] AI Dispatch will run every {day.capitalize()} at {hour:02d}:{minute:02d} IST")
    print("[Scheduler] Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\n[Scheduler] Stopped.")


if __name__ == "__main__":
    start_scheduler()
