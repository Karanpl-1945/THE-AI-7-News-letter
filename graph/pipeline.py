"""LangGraph pipeline — the central state machine that orchestrates all agents."""

import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import TypedDict, List, Dict, Any, Optional, cast
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from langfuse import observe


class NewsletterState(TypedDict):
    # Raw collected data
    papers:            List[Dict[str, Any]]
    model_news:        List[Dict[str, Any]]
    github_trends:     List[Dict[str, Any]]
    news_items:        List[Dict[str, Any]]
    framework_updates: List[Dict[str, Any]]
    # Deterministically selected data allowed to reach Groq
    selected_papers:     List[Dict[str, Any]]
    selected_models:     List[Dict[str, Any]]
    selected_github:     List[Dict[str, Any]]
    selected_news:       List[Dict[str, Any]]
    selected_frameworks: List[Dict[str, Any]]
    # Summarised data
    summarized_papers:     List[Dict[str, Any]]
    summarized_models:     List[Dict[str, Any]]
    summarized_github:     List[Dict[str, Any]]
    summarized_news:       List[Dict[str, Any]]
    summarized_frameworks: List[Dict[str, Any]]
    # Editorial output
    editorial: Dict[str, Any]
    # Rendered output
    html_content: str
    html_path:    Optional[str]
    pdf_path:     Optional[str]
    html_object_key: Optional[str]
    pdf_object_key:  Optional[str]
    admin_notified: bool
    editorial_feedback: Optional[str]
    revision_number: int
    review_decision: Optional[str]
    send_result: Optional[Dict[str, Any]]
    # Metadata
    issue_date:   str
    week_number:  int
    dry_run:      bool
    issue_id:     str
    workflow_run_id: str
    thread_id:    str
    issue_key:    str


# ── NODE FUNCTIONS ────────────────────────────────────────

def _html_output_path(issue_date: str) -> Path:
    """Return the local HTML path for the current execution environment."""
    safe_date = issue_date.replace(" ", "_").replace(",", "")
    return Path(__file__).resolve().parent.parent / "output" / f"ai_dispatch_{safe_date}.html"


def _ensure_local_artifacts(state: NewsletterState) -> tuple[str, str]:
    """Restore checkpointed HTML/PDF files when resuming on a new runner."""
    from formatter.pdf_generator import html_to_pdf

    html_content = state.get("html_content", "")
    saved_html_path = state.get("html_path")
    html_path = Path(saved_html_path) if saved_html_path else None
    if html_path is None or not html_path.is_file():
        if not html_content:
            raise RuntimeError("Checkpoint has no HTML content to restore artifacts.")
        html_path = _html_output_path(state["issue_date"])
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html_content, encoding="utf-8")
        print(f"  Restored HTML from checkpoint: {html_path}")

    saved_pdf_path = state.get("pdf_path")
    pdf_path = Path(saved_pdf_path) if saved_pdf_path else None
    if pdf_path is None or not pdf_path.is_file():
        if not html_content:
            raise RuntimeError("Checkpoint has no HTML content to regenerate the PDF.")
        regenerated_pdf = html_to_pdf(html_content, state["issue_date"])
        pdf_path = Path(regenerated_pdf) if regenerated_pdf else None
        if pdf_path is None or not pdf_path.is_file():
            raise RuntimeError("PDF restoration from checkpointed HTML failed.")
        print(f"  Regenerated PDF from checkpoint: {pdf_path}")

    return str(html_path), str(pdf_path)

@observe(name="collect", as_type="chain")
def node_collect(state: NewsletterState) -> NewsletterState:
    """Run all five data-collection agents in parallel threads."""
    from agents.paper_agent         import fetch_papers
    from agents.model_watcher       import fetch_model_news
    from agents.github_tracker      import fetch_github_trends
    from agents.news_agent          import fetch_news
    from agents.framework_doc_agent import fetch_framework_updates

    print("\n[Pipeline] Step 1/8 — Collecting data from all sources...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            "papers":     ex.submit(fetch_papers),
            "models":     ex.submit(fetch_model_news),
            "github":     ex.submit(fetch_github_trends),
            "news":       ex.submit(fetch_news),
            "frameworks": ex.submit(fetch_framework_updates),
        }
        results = {k: f.result() for k, f in futures.items()}

    print(f"  Papers: {len(results['papers'])} | Models: {len(results['models'])} | "
          f"GitHub: {len(results['github'])} | News: {len(results['news'])} | "
          f"Frameworks: {len(results['frameworks'])}")

    return {
        **state,
        "papers":            results["papers"],
        "model_news":        results["models"],
        "github_trends":     results["github"],
        "news_items":        results["news"],
        "framework_updates": results["frameworks"],
    }


@observe(name="preselect", as_type="chain")
def node_preselect(state: NewsletterState) -> NewsletterState:
    """Rank, cap, and diversify items before making any Groq calls."""
    from agents.preselector import preselect_for_summarization

    print("\n[Pipeline] Step 2/8 — Preselecting items for the Groq budget...")
    selected = preselect_for_summarization(state)
    print(
        f"  Selected — Papers: {len(selected['selected_papers'])} | "
        f"Models: {len(selected['selected_models'])} | "
        f"GitHub: {len(selected['selected_github'])} | "
        f"News: {len(selected['selected_news'])} | "
        f"Frameworks: {len(selected['selected_frameworks'])}"
    )
    return {**state, **selected}


@observe(name="summarize", as_type="chain")
def node_summarize(state: NewsletterState) -> NewsletterState:
    """Summarise each item using Groq."""
    from agents.summarizer import summarize_items

    print("\n[Pipeline] Step 3/8 — Summarising selected items with Groq...")

    return {
        **state,
        "summarized_papers":     summarize_items(state["selected_papers"],     "paper"),
        "summarized_models":     summarize_items(state["selected_models"],     "model"),
        "summarized_github":     summarize_items(state["selected_github"],     "github"),
        "summarized_news":       summarize_items(state["selected_news"],       "news"),
        "summarized_frameworks": summarize_items(state["selected_frameworks"], "framework"),
    }


@observe(name="edit", as_type="chain")
def node_edit(state: NewsletterState) -> NewsletterState:
    """Editor agent: curate, rank, and generate all special features."""
    from agents.editor import create_editorial

    print("\n[Pipeline] Step 4/8 — Editor agent running...")
    editorial = create_editorial(state)
    return {**state, "editorial": editorial}


@observe(name="format", as_type="chain")
def node_format(state: NewsletterState) -> NewsletterState:
    """Render the Jinja2 HTML template."""
    from formatter.formatter import render_newspaper

    print("\n[Pipeline] Step 5/8 — Rendering HTML newspaper...")
    html = render_newspaper(state)

    html_path = _html_output_path(state["issue_date"])
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    print(f"  HTML saved to {html_path}")

    return {**state, "html_content": html, "html_path": str(html_path)}


@observe(name="pdf", as_type="chain")
def node_pdf(state: NewsletterState) -> NewsletterState:
    """Convert HTML to PDF."""
    from formatter.pdf_generator import html_to_pdf

    print("\n[Pipeline] Step 6/8 — Generating PDF...")
    pdf_path = html_to_pdf(state["html_content"], state["issue_date"])
    return {**state, "pdf_path": pdf_path}


@observe(name="publish", as_type="tool")
def node_publish(state: NewsletterState) -> NewsletterState:
    """Upload generated HTML and PDF to private R2 and record them in Neon."""
    from storage.artifact_service import reconcile_artifacts

    print("\n[Pipeline] Step 7/8 — Publishing HTML and PDF to private R2...")
    html_path, pdf_path = _ensure_local_artifacts(state)

    issue_id = UUID(state["issue_id"])
    workflow_run_id = UUID(state["workflow_run_id"])
    artifacts = reconcile_artifacts(
        issue_id=issue_id,
        workflow_run_id=workflow_run_id,
        html_path=html_path,
        pdf_path=pdf_path,
    )
    print(f"  HTML object: {artifacts['html'].object_key}")
    print(f"  PDF object:  {artifacts['pdf'].object_key}")
    return {
        **state,
        "html_path": html_path,
        "pdf_path": pdf_path,
        "html_object_key": artifacts["html"].object_key,
        "pdf_object_key": artifacts["pdf"].object_key,
    }


@observe(name="notify_admin", as_type="tool")
def node_notify_admin(state: NewsletterState) -> NewsletterState:
    """Email the admin a preview and mark the issue as awaiting review.

    Reads `revision_number` from state rather than taking it as a parameter —
    LangGraph only ever calls node functions with the single state argument,
    so this node needs to be self-contained to work when the graph itself
    (re-)invokes it via the approval → edit → ... → notify_admin loop.
    """
    from delivery.email_sender import send_admin_review_email

    print("\n[Pipeline] Step 8/8 — Notifying admin for review...")
    html_path, pdf_path = _ensure_local_artifacts(state)
    notified = send_admin_review_email(
        state["html_content"],
        pdf_path,
        state["issue_date"],
        issue_key=state["issue_key"],
        revision_number=state.get("revision_number", 1),
    )
    return {
        **state,
        "html_path": html_path,
        "pdf_path": pdf_path,
        "admin_notified": notified,
    }


def route_after_publish(state: NewsletterState) -> str:
    """Skip the admin notification when generating a dry-run preview."""
    if state["dry_run"]:
        print("\n[Pipeline] Step 8/8 — Dry run: admin notification skipped.")
        return "finish"
    return "notify_admin"


@observe(name="approval", as_type="tool")
def node_approval(state: NewsletterState) -> NewsletterState:
    """Pause the graph here until the admin resumes with a decision.

    `interrupt()` suspends execution and checkpoints the graph at this exact
    point; resuming with `Command(resume={"decision": ..., "feedback": ...})`
    re-enters this node with that payload as the return value.
    """
    print("\n[Pipeline] Awaiting admin decision (approve / request_changes)...")
    payload = interrupt({"issue_key": state["issue_key"]})
    decision = payload["decision"]
    updates: Dict[str, Any] = {
        "review_decision": decision,
        "editorial_feedback": payload.get("feedback"),
    }
    if decision == "request_changes":
        updates["revision_number"] = state.get("revision_number", 1) + 1
    return {**state, **updates}


def route_after_approval(state: NewsletterState) -> str:
    """Approve moves on to sending; request_changes loops back to the editor."""
    if state["review_decision"] == "approve":
        return "send"
    return "edit"


@observe(name="send", as_type="tool")
def node_send(state: NewsletterState) -> NewsletterState:
    """Deliver the approved issue to every active subscriber."""
    from delivery.broadcast import send_to_subscribers

    print("\n[Pipeline] Sending to subscribers...")
    result = send_to_subscribers(state, UUID(state["issue_id"]))
    print(f"  Sent: {result['sent']} | Failed: {result['failed']} | Skipped: {result['skipped']}")
    return {**state, "send_result": result}


# ── BUILD GRAPH ───────────────────────────────────────────

def build_pipeline(checkpointer: BaseCheckpointSaver | None = None):
    """Build the graph, optionally persisting node state with a checkpointer."""
    graph = StateGraph(NewsletterState)

    graph.add_node("collect",   node_collect)
    graph.add_node("preselect", node_preselect)
    graph.add_node("summarize", node_summarize)
    graph.add_node("edit",      node_edit)
    graph.add_node("format",    node_format)
    graph.add_node("pdf",       node_pdf)
    graph.add_node("publish",      node_publish)
    graph.add_node("notify_admin", node_notify_admin)
    graph.add_node("approval",     node_approval)
    graph.add_node("send",         node_send)

    graph.set_entry_point("collect")
    graph.add_edge("collect",   "preselect")
    graph.add_edge("preselect", "summarize")
    graph.add_edge("summarize", "edit")
    graph.add_edge("edit",      "format")
    graph.add_edge("format",    "pdf")
    graph.add_edge("pdf",       "publish")
    graph.add_conditional_edges(
        "publish",
        route_after_publish,
        {"notify_admin": "notify_admin", "finish": END},
    )
    graph.add_edge("notify_admin", "approval")
    graph.add_conditional_edges(
        "approval",
        route_after_approval,
        {"send": "send", "edit": "edit"},
    )
    graph.add_edge("send", END)

    return graph.compile(checkpointer=checkpointer)


def build_thread_id(now: datetime, force: bool = False) -> str:
    """Return one stable checkpoint thread per ISO week.

    A forced run receives a unique suffix so it cannot overwrite or resume the
    normal weekly execution.
    """
    iso_year, iso_week, _ = now.isocalendar()
    weekly_id = f"newsletter-{iso_year}-W{iso_week:02d}"
    if force:
        return f"{weekly_id}-forced-{now.strftime('%Y%m%dT%H%M%S%f')}"
    return weekly_id


def invoke_checkpointed_pipeline(
    pipeline,
    initial_state: NewsletterState,
    config: Dict[str, Any],
) -> NewsletterState:
    """Start, resume, or reuse a pipeline execution based on its checkpoint."""
    snapshot = pipeline.get_state(config)

    if not snapshot.values:
        print("[Checkpoint] No saved state found; starting a new run.")
        return cast(
            NewsletterState,
            pipeline.invoke(initial_state, config=config),
        )

    if snapshot.next:
        pending_nodes = ", ".join(snapshot.next)
        print(f"[Checkpoint] Resuming pending node(s): {pending_nodes}")
        return cast(
            NewsletterState,
            pipeline.invoke(None, config=config),
        )

    print("[Checkpoint] This weekly run is already complete; reusing saved state.")
    saved_state = dict(snapshot.values)
    if saved_state.get("html_content"):
        from storage.artifact_service import reconcile_artifacts

        html_path, pdf_path = _ensure_local_artifacts(
            cast(NewsletterState, saved_state)
        )
        saved_state["html_path"] = html_path
        saved_state["pdf_path"] = pdf_path
        artifacts = reconcile_artifacts(
            issue_id=UUID(saved_state["issue_id"]),
            workflow_run_id=UUID(saved_state["workflow_run_id"]),
            html_path=html_path,
            pdf_path=pdf_path,
        )
        saved_state["html_object_key"] = artifacts["html"].object_key
        saved_state["pdf_object_key"] = artifacts["pdf"].object_key
    return cast(NewsletterState, saved_state)


@observe(name="weekly_newsletter_pipeline", as_type="agent")
def run_pipeline(dry_run: bool = False, force: bool = False) -> NewsletterState:
    from database.checkpointer import postgres_checkpointer
    from database.workflow_repository import (
        begin_workflow_run,
        complete_workflow_run,
        fail_workflow_run,
    )
    from observability import configure_langfuse

    configure_langfuse()
    now = datetime.now()
    iso_year, iso_week, _ = now.isocalendar()
    issue_key = f"{iso_year}-W{iso_week:02d}"
    thread_id = build_thread_id(now, force=force)
    tracking = begin_workflow_run(
        issue_key=issue_key,
        issue_date=now.date(),
        iso_year=iso_year,
        iso_week=iso_week,
        thread_id=thread_id,
        dry_run=dry_run,
    )
    initial_state: NewsletterState = {
        "papers": [], "model_news": [], "github_trends": [],
        "news_items": [], "framework_updates": [],
        "selected_papers": [], "selected_models": [],
        "selected_github": [], "selected_news": [],
        "selected_frameworks": [],
        "summarized_papers": [], "summarized_models": [],
        "summarized_github": [], "summarized_news": [],
        "summarized_frameworks": [],
        "editorial": {},
        "html_content": "",
        "html_path": None,
        "pdf_path": None,
        "html_object_key": None,
        "pdf_object_key": None,
        "admin_notified": False,
        "editorial_feedback": None,
        "revision_number": 1,
        "review_decision": None,
        "send_result": None,
        "issue_date":  now.strftime("%B %d, %Y"),
        "week_number": iso_week,
        "dry_run": dry_run,
        "issue_id": str(tracking.issue_id),
        "workflow_run_id": str(tracking.run_id),
        "thread_id": thread_id,
        "issue_key": issue_key,
    }

    config = {"configurable": {"thread_id": thread_id}}
    print("=" * 60)
    print("  THE AI DISPATCH — Weekly Newspaper Pipeline")
    print(f"  Checkpoint thread: {thread_id}")
    print("=" * 60)
    try:
        with postgres_checkpointer() as checkpointer:
            pipeline = build_pipeline(checkpointer=checkpointer)
            result = invoke_checkpointed_pipeline(pipeline, initial_state, config)
    except Exception as error:
        try:
            fail_workflow_run(tracking, error)
        except Exception as tracking_error:
            print(f"[Workflow] Could not record pipeline failure: {tracking_error}")
        raise

    complete_workflow_run(tracking, admin_notified=result["admin_notified"])
    print("\n" + "=" * 60)
    print(f"  Done! Admin notified: {result['admin_notified']}")
    print(f"  PDF:  {result.get('pdf_path', 'N/A')}")
    print(f"  R2 PDF object: {result.get('pdf_object_key', 'N/A')}")
    print("=" * 60)
    return result
