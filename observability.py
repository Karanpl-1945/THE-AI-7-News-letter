"""Langfuse and Groq observability setup."""

from langfuse import get_client


_configured = False


def configure_langfuse() -> None:
    """Initialize Langfuse and instrument the Groq SDK once per process."""
    global _configured
    if _configured:
        return

    from openinference.instrumentation.groq import GroqInstrumentor

    GroqInstrumentor().instrument()
    _configured = True


def flush_langfuse() -> None:
    """Export queued observations before a short-lived process exits."""
    get_client().flush()
