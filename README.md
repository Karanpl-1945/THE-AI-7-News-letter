# ⚡ THE AI 7 — Your Weekly AI Intelligence Brief

A fully automated AI newspaper delivered to your inbox, covering the latest in AI research, model releases, GitHub trends, and framework updates — powered by **Groq**, **LangGraph**, **PostgreSQL**, and **Cloudflare R2**, and scheduled via **GitHub Actions**.

---

## What You Get

Every scheduled run, a beautifully formatted newspaper lands in your inbox (HTML + PDF) with:

| Section | What it contains |
|---|---|
| ⚡ TL;DR | 5 bullet summary of the entire week |
| 🏆 Editor's Pick | Single most important story, with why it matters |
| 📄 Research Papers | Top 5 ArXiv papers with difficulty rating & summaries |
| 🤖 Model Releases | New models from OpenAI, Anthropic, Google, Meta, HuggingFace |
| 📌 Paper of the Week | One paper explained in full depth (problem → approach → results → implications) |
| ⭐ GitHub Trending | Top repos gaining stars this week in AI/ML |
| ⚙️ Framework Updates | New releases of LangChain, LangGraph, CrewAI, vLLM, Ollama, etc. |
| 🛠️ Tool of the Week | Deep dive into one tool with install command + quickstart code |
| 📰 AI News | Top stories from OpenAI, Anthropic, Google AI, The Batch, Import AI |
| 🔥 Trending Topics | Tag cloud of buzzwords dominating the week |
| 📚 Learning Paths | "Read these to understand this week's big topics" |
| 🔤 Glossary | New terms introduced this week, explained simply |

---

## Architecture

The production path is a **GitHub Actions cron** that runs `python main.py --dry-run` daily
(see `.github/workflows/weekly-newsletter.yml`). `scheduler/runner.py` (APScheduler) still
exists as an alternative way to run the pipeline continuously on your own machine, but it is
not what the scheduled CI workflow uses.

```
[GitHub Actions cron]  (or scheduler/runner.py locally)
         │
         ▼
[Orchestrator — LangGraph Pipeline, checkpointed per ISO week in PostgreSQL]
         │
   ┌─────┼──────────────────────────────┐
   ▼     ▼          ▼          ▼        ▼
Paper  Model     GitHub     News    Framework
Agent  Watcher   Tracker    Agent   Doc Agent
   └─────┼──────────────────────────────┘
         │  (parallel threads)
         ▼
[Preselector]        ← deterministic scoring/dedup/diversity caps, no LLM calls
         │
         ▼
[Summarizer Agent]   ← Groq enriches each selected item
         │
         ▼
[Editor Agent]       ← Groq curates, ranks, writes features
         │
         ▼
[Formatter]          ← Jinja2 renders HTML newspaper
         │
         ▼
[PDF Generator]      ← WeasyPrint converts HTML → PDF
         │
         ▼
[Publisher]          ← uploads HTML/PDF to Cloudflare R2, records in PostgreSQL
         │
         ▼
[Email Delivery]     ← Gmail SMTP sends to your inbox (skipped on --dry-run)
```

### Agent Roles

| Agent | File | What it does |
|---|---|---|
| **Paper Agent** | `agents/paper_agent.py` | Fetches papers from ArXiv (`cs.AI`, `cs.LG`, `cs.CL`, `stat.ML`) and Papers With Code |
| **Model Watcher** | `agents/model_watcher.py` | Monitors RSS feeds from OpenAI, Anthropic, Google, Meta, HuggingFace, Mistral, Cohere |
| **GitHub Tracker** | `agents/github_tracker.py` | Scrapes GitHub Trending + fetches new releases from watched repos |
| **News Agent** | `agents/news_agent.py` | Parses RSS feeds and community sources configured in `config/sources.yaml` |
| **Framework Doc Agent** | `agents/framework_doc_agent.py` | Monitors LangChain, LangGraph, CrewAI, vLLM, Ollama, NeMo, and more for new releases |
| **Preselector** | `agents/preselector.py` | Deterministically dedupes and scores every item (freshness/relevance/credibility/completeness/activity/reproducibility) before any LLM call, applying per-category limits and per-source diversity caps from `config/sources.yaml` |
| **Summarizer** | `agents/summarizer.py` | Groq call per selected item → adds summary, why_it_matters, key_takeaway, difficulty |
| **Editor** | `agents/editor.py` | Groq selects top stories, writes TL;DR, Paper of Week, Tool of Week, Glossary |
| **Formatter** | `formatter/formatter.py` | Jinja2 renders `newspaper.html` template with all curated content |
| **PDF Generator** | `formatter/pdf_generator.py` | WeasyPrint converts HTML → PDF and saves to `output/` |
| **Publisher** | `storage/artifact_service.py` + `storage/r2_client.py` | Uploads generated HTML/PDF to a private Cloudflare R2 bucket, reconciling against existing objects instead of blindly re-uploading |
| **Email Sender** | `delivery/email_sender.py` | Gmail SMTP sends HTML body + PDF attachment to a single configured recipient |
| **Pipeline** | `graph/pipeline.py` | LangGraph StateGraph connecting all nodes, checkpointed to PostgreSQL per ISO week (`database/checkpointer.py`) |
| **Scheduler (GitHub Actions)** | `.github/workflows/weekly-newsletter.yml` | Cron-triggered CI workflow that runs the pipeline in `--dry-run` mode and uploads the HTML/PDF as a build artifact |
| **Scheduler (local, alternative)** | `scheduler/runner.py` | APScheduler runs the pipeline on a configured day/time if you prefer to run it yourself instead of via CI |

---

## Project Structure

```
ai-newspaper/
├── agents/
│   ├── paper_agent.py          # ArXiv + Papers With Code
│   ├── model_watcher.py        # AI company blog RSS feeds
│   ├── github_tracker.py       # GitHub Trending + release watcher
│   ├── news_agent.py           # AI news RSS + community sources
│   ├── framework_doc_agent.py  # Framework release monitor
│   ├── preselector.py          # Deterministic scoring, dedup, diversity caps
│   ├── summarizer.py           # Groq enrichment per selected item
│   └── editor.py               # Groq curation + features
├── formatter/
│   ├── formatter.py            # Jinja2 HTML renderer
│   ├── pdf_generator.py        # HTML → PDF via WeasyPrint
│   └── templates/
│       └── newspaper.html      # Newspaper template (CSS + Jinja2)
├── graph/
│   └── pipeline.py             # LangGraph StateGraph + checkpointed invocation
├── database/
│   ├── connection.py           # PostgreSQL connection boundary
│   ├── migrate.py              # Schema migrator
│   ├── checkpointer.py         # LangGraph PostgresSaver wrapper
│   ├── summary_repository.py   # Content-hash keyed summary cache
│   ├── workflow_repository.py  # Workflow-run tracking
│   ├── artifact_repository.py  # R2 artifact bookkeeping
│   └── migrations/*.sql        # Schema migrations
├── storage/
│   ├── r2_client.py            # Cloudflare R2 (S3-compatible) client
│   └── artifact_service.py     # Reconcile-before-reupload publishing logic
├── llm/
│   └── groq_client.py          # Rate-limit-aware Groq request gateway
├── delivery/
│   └── email_sender.py         # Gmail SMTP delivery
├── scheduler/
│   └── runner.py               # APScheduler local-runner alternative to GitHub Actions
├── config/
│   └── sources.yaml            # Data sources, repos, RSS feeds, preselection weights
├── .github/workflows/
│   └── weekly-newsletter.yml   # Scheduled CI workflow (dry-run generation)
├── observability.py             # Langfuse + Groq instrumentation
├── output/                     # Generated HTML + PDF files (auto-created)
├── tests/                      # Unit tests (unittest / run with `python -m unittest`)
├── .env.example                # Template for secrets
├── requirements.txt
└── main.py                     # Run once manually (`--dry-run` skips email)
```

---

## Setup — Step by Step

### 1. Clone / Navigate to the project

```bash
cd "ai-newspaper"
```

### 2. Create a virtual environment and install dependencies

This project uses **uv** (fast Python package manager):

```bash
uv venv venv --python 3.12
uv pip install -r requirements.txt --python venv/bin/python3
```

Then activate the environment before running any commands:
```bash
source venv/bin/activate        # Linux / Mac
venv\Scripts\activate           # Windows
```

> **Don't have uv?** Install it with:
> ```bash
> curl -Lsf https://astral.sh/uv/install.sh | sh
> ```

### 4. Get your API keys and services

| Key | Where to get it | Cost |
|---|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | Free tier available |
| `DATABASE_URL` | Any PostgreSQL provider (e.g. Neon, Supabase, local Postgres) | Free tier available |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET_NAME` | Cloudflare dashboard → R2 → create a bucket + API token | Free tier available |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | [cloud.langfuse.com](https://cloud.langfuse.com) | Free tier available |
| `GITHUB_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) → Generate new token (classic) → no scopes needed | Free |
| Gmail App Password | Google Account → Security → 2-Step Verification → App passwords | Free |

### 5. Configure your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in the values described in `.env.example` — Groq, PostgreSQL, Cloudflare
R2, Langfuse, GitHub, Gmail, and personalisation settings all live there.

### 6. Initialize the database once

```bash
python -m database.checkpointer
python -m database.migrate
```

### 7. Test it once

```bash
python main.py --dry-run
```

This runs the full pipeline immediately, generates HTML + PDF, uploads them to R2, and skips
email. Check the `output/` folder for the saved files, then run without `--dry-run` once you're
ready to actually send an email.

### 8. Automate it

The included `.github/workflows/weekly-newsletter.yml` runs the pipeline on a GitHub Actions
cron schedule (currently daily at 8:00 AM IST, in `--dry-run` mode) — set the required secrets
and variables in your repo settings and it runs without you keeping anything online yourself.

If you'd rather run it continuously on your own machine instead of via CI, use the APScheduler
alternative:

```bash
python scheduler/runner.py
```

Leave this running in the background — it triggers at the day/time configured via
`SCHEDULE_DAY` / `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` in `.env`.

> **Tip for keeping it running:** Use `tmux` or `screen` so it survives terminal close:
> ```bash
> tmux new -s newspaper
> python scheduler/runner.py
> # Press Ctrl+B then D to detach. It keeps running.
> ```

---

## Customisation

### Add or remove data sources

Edit `config/sources.yaml`:

```yaml
github:
  watch_repos:
    - langchain-ai/langgraph    # add any repo you want to watch
    - your-org/your-repo

rss_feeds:
  ai_blogs:
    - name: "Some Blog"
      url: "https://someblog.com/feed.xml"
```

### Change your interests or skill level

Edit `.env`:

```env
USER_INTERESTS=reinforcement learning,robotics,NLP
SKILL_LEVEL=beginner
```

Groq's summariser and editor will adapt their language and selections accordingly, and the
`preselector` also uses `USER_INTERESTS` when scoring items for relevance.

### Change delivery day/time (local `scheduler/runner.py` only)

```env
SCHEDULE_DAY=saturday
SCHEDULE_HOUR=9
SCHEDULE_MINUTE=30
```

This only affects the APScheduler-based local runner. If you're using the GitHub Actions
workflow instead, change the `cron:` line in `.github/workflows/weekly-newsletter.yml` (schedule
times there are in UTC).

---

## How the LangGraph Pipeline Works

LangGraph treats the newspaper as a **state machine**. Each node is a Python function that receives the full state dictionary, does its work, and returns an updated state. The state flows through nodes in sequence:

```
collect → preselect → summarize → edit → format → pdf → publish → email → END
```

(`email` is skipped and the graph ends after `publish` when running with `--dry-run`.)

The `collect` node runs all 5 data agents in **parallel threads** using `concurrent.futures`, so fetching takes the time of the slowest agent, not the sum of all agents. The pipeline is checkpointed to PostgreSQL per ISO week (`database/checkpointer.py`), so a failed or interrupted run resumes from the last completed node instead of starting over, and a completed week's run is reused rather than regenerated.

You can visualise the graph by adding this to `graph/pipeline.py`:

```python
pipeline = build_pipeline()
print(pipeline.get_graph().draw_ascii())
```

---

## Cost Estimate

| Item | Cost |
|---|---|
| Groq API (run, ~20-30 items) | Free tier covers typical usage |
| PostgreSQL (Neon/Supabase free tier) | Free |
| Cloudflare R2 storage | Free tier covers typical usage |
| Langfuse observability | Free tier |
| GitHub API | Free |
| ArXiv, RSS, Papers With Code | Free |
| Gmail SMTP | Free |
| GitHub Actions minutes | Free tier covers a daily run comfortably |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `[Error] Missing environment variables: ...` | Make sure `.env` exists and includes `GROQ_API_KEY`, `DATABASE_URL`, and all `R2_*` keys (plus `EMAIL_SENDER`/`EMAIL_PASSWORD` when not using `--dry-run`) |
| `EMAIL_SENDER or EMAIL_PASSWORD not set` | Make sure `.env` file exists and `load_dotenv()` ran |
| Gmail authentication failed | Use an **App Password**, not your regular Gmail password. Enable 2FA first. |
| WeasyPrint install error | Install system Pango libraries (see Step 3 above) |
| GitHub API rate limit | Add `GITHUB_TOKEN` to `.env` (raises limit from 60 to 5000 req/hour) |
| No papers found | Check your internet connection; ArXiv may be temporarily slow |
| PDF is blank/broken | Some WeasyPrint versions need `libpangoft2`. Run `sudo apt install libpangoft2-1.0-0` |
| `[Database] Connection failed` | Check `DATABASE_URL` and run `python -m database.migrate` again |
| `[R2] Connection failed` | Check the `R2_*` credentials and that the bucket exists |

---

## Learning Resources

Since this project is built for learning, here's what each component teaches:

| Component | Concepts you learn |
|---|---|
| `agents/paper_agent.py` | Working with APIs, data parsing, deduplication |
| `agents/preselector.py` | Deterministic scoring/ranking, dedup heuristics, diversity constraints |
| `agents/summarizer.py` | Prompt engineering, Groq API, JSON structured output |
| `agents/editor.py` | Multi-step LLM reasoning, chained prompts |
| `graph/pipeline.py` | LangGraph StateGraph, typed state, agent orchestration, checkpointing |
| `database/` | PostgreSQL schema design, migrations, LangGraph checkpointer integration |
| `storage/` | S3-compatible object storage, idempotent publish/reconcile logic |
| `llm/groq_client.py` | Rate limiting, exponential backoff, quota handling |
| `observability.py` | LLM tracing with Langfuse |
| `formatter/templates/newspaper.html` | Jinja2 templating, CSS layout, print-friendly design |
| `delivery/email_sender.py` | MIME email, SMTP, file attachments |
| `.github/workflows/weekly-newsletter.yml` | GitHub Actions cron scheduling, CI secrets/variables |
| `scheduler/runner.py` | APScheduler, cron triggers, background automation (local alternative) |
