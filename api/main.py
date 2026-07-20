"""Thin HTTP front door onto the newsletter pipeline: review links + subscriber management."""

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from api.routers import review, subscribers

app = FastAPI(title="THE AI 7 — Review & Subscribers API")
app.include_router(review.router)
app.include_router(subscribers.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
