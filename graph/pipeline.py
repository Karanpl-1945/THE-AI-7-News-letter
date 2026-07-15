"""LangGraph pipeline — the central state machine that orchestrates all agents."""

import concurrent.futures
from datetime import datetime
from typing import TypedDict, List, Dict, Any, Optional, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph, END
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
    pdf_path:     Optional[str]
    email_sent:   bool
    # Metadata
    issue_date:   str
    week_number:  int
    dry_run:      bool


# ── NODE FUNCTIONS ────────────────────────────────────────

@observe(name="collect", as_type="chain")
def node_collect(state: NewsletterState) -> NewsletterState:
    """Run all five data-collection agents in parallel threads."""
    from agents.paper_agent         import fetch_papers
    from agents.model_watcher       import fetch_model_news
    from agents.github_tracker      import fetch_github_trends
    from agents.news_agent          import fetch_news
    from agents.framework_doc_agent import fetch_framework_updates

    print("\n[Pipeline] Step 1/7 — Collecting data from all sources...")

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

    print("\n[Pipeline] Step 2/7 — Preselecting items for the Groq budget...")
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

    print("\n[Pipeline] Step 3/7 — Summarising selected items with Groq...")

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

    print("\n[Pipeline] Step 4/7 — Editor agent running...")
    editorial = create_editorial(state)
    return {**state, "editorial": editorial}


@observe(name="format", as_type="chain")
def node_format(state: NewsletterState) -> NewsletterState:
    """Render the Jinja2 HTML template."""
    from formatter.formatter import render_newspaper

    print("\n[Pipeline] Step 5/7 — Rendering HTML newspaper...")
    html = render_newspaper(state)

    # Save HTML to output/
    import os
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)
    safe_date = state["issue_date"].replace(" ", "_").replace(",", "")
    html_path = os.path.join(output_dir, f"ai_dispatch_{safe_date}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML saved to {html_path}")

    return {**state, "html_content": html}


@observe(name="pdf", as_type="chain")
def node_pdf(state: NewsletterState) -> NewsletterState:
    """Convert HTML to PDF."""
    from formatter.pdf_generator import html_to_pdf

    print("\n[Pipeline] Step 6/7 — Generating PDF...")
    pdf_path = html_to_pdf(state["html_content"], state["issue_date"])
    return {**state, "pdf_path": pdf_path}


@observe(name="email", as_type="tool")
def node_email(state: NewsletterState) -> NewsletterState:
    """Send the newspaper by email."""
    from delivery.email_sender import send_newspaper

    print("\n[Pipeline] Step 7/7 — Sending email...")
    sent = send_newspaper(state["html_content"], state.get("pdf_path"), state["issue_date"])
    return {**state, "email_sent": sent}


def route_after_pdf(state: NewsletterState) -> str:
    """Skip delivery when generating a dry-run preview."""
    if state["dry_run"]:
        print("\n[Pipeline] Step 7/7 — Dry run: email skipped.")
        return "finish"
    return "email"


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
    graph.add_node("email",     node_email)

    graph.set_entry_point("collect")
    graph.add_edge("collect",   "preselect")
    graph.add_edge("preselect", "summarize")
    graph.add_edge("summarize", "edit")
    graph.add_edge("edit",      "format")
    graph.add_edge("format",    "pdf")
    graph.add_conditional_edges(
        "pdf",
        route_after_pdf,
        {"email": "email", "finish": END},
    )
    graph.add_edge("email",     END)

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
    return cast(NewsletterState, snapshot.values)


@observe(name="weekly_newsletter_pipeline", as_type="agent")
def run_pipeline(dry_run: bool = False, force: bool = False) -> NewsletterState:
    from database.checkpointer import postgres_checkpointer
    from observability import configure_langfuse

    configure_langfuse()
    now = datetime.now()
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
        "pdf_path": None,
        "email_sent": False,
        "issue_date":  now.strftime("%B %d, %Y"),
        "week_number": now.isocalendar()[1],
        "dry_run": dry_run,
    }

    thread_id = build_thread_id(now, force=force)
    config = {"configurable": {"thread_id": thread_id}}
    print("=" * 60)
    print("  THE AI DISPATCH — Weekly Newspaper Pipeline")
    print(f"  Checkpoint thread: {thread_id}")
    print("=" * 60)
    with postgres_checkpointer() as checkpointer:
        pipeline = build_pipeline(checkpointer=checkpointer)
        result = invoke_checkpointed_pipeline(pipeline, initial_state, config)
    print("\n" + "=" * 60)
    print(f"  Done! Email sent: {result['email_sent']}")
    print(f"  PDF:  {result.get('pdf_path', 'N/A')}")
    print("=" * 60)
    return result
