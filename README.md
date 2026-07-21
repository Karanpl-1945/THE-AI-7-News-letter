# ⚡ THE AI 7 — Your Weekly AI Intelligence Brief

A fully automated AI newspaper delivered to your inbox every Sunday, covering the latest in AI
research, model releases, GitHub trends, and framework updates — powered by **Groq**,
**LangGraph**, **PostgreSQL**, and **Cloudflare R2**, scheduled via **GitHub Actions**, with a
**human-in-the-loop admin review** before anything reaches subscribers.

---

## What You Get

Every Sunday, a 5-page newspaper is generated (HTML + PDF), one section building on the last:

| Page | Sections |
|---|---|
| **1 — Open** | Masthead, ⚡ TL;DR (5 bullets), 📌 **Paper of the Week** — the week's top paper in full: problem → approach → results → why it matters → one-line takeaway |
| **2 — Research** | 📄 Top Research Papers (3-4 full write-ups: difficulty badge, summary, why it matters, takeaway), 🔭 Research Radar — one-liners on other papers worth knowing about |
| **3 — Tooling & Infrastructure** | ⭐ GitHub Trending, ⚙️ Framework & Tool Updates, 🧩 Emerging Patterns & Infra — new RAG/retrieval/vector-DB techniques, when genuinely found that week |
| **4 — Applied** | 🤖 New Models & Releases, 🛠 Production Playbook — one real-world build or postmortem, 🔧 **Tool of the Week** — install command + quickstart, only shown when genuinely populated |
| **5 — Extras** | 🔍 Under the Radar (one non-obvious pick + reasoning), ⚡ Quick Hits (3-5 one-liners), then 🔥 Trending Topics / 🔤 Glossary / 📚 Learning Paths — best-effort, so their occasional absence never reads as broken |

An admin reviews every draft before it ships — approving it, or sending it back with feedback
for another pass — and only approved issues ever reach subscribers.

---

## Architecture

The production path is a **GitHub Actions cron** (Sundays, 8 AM IST) that runs `python main.py`,
generating the issue and pausing for review — it does **not** email subscribers directly.
A second, small **FastAPI service** (deployed separately, e.g. on Render) gives the admin
one-tap Approve/Request-Changes buttons and a public subscribe page; the same decision can also
be applied via a manual GitHub Actions workflow or a local CLI command, so nothing depends on
the API service staying up.

```
[GitHub Actions cron — Sundays 8 AM IST]
              │
              ▼
[LangGraph pipeline, checkpointed per ISO week in PostgreSQL]
              │
   ┌──────────┼───────────────────────────────┐
   ▼          ▼            ▼            ▼      ▼
 Paper      Model        GitHub        News  Framework
 Agent     Watcher      Tracker       Agent  Doc Agent
   └──────────┼───────────────────────────────┘
              │  (parallel threads)
              ▼
      [Preselector]   ← deterministic scoring/dedup/diversity caps, no LLM calls
              ▼
      [Summarizer]    ← Groq enriches each selected item (cached by content hash)
              ▼
   ┌─────────►[Editor]        ← Groq curates, ranks, writes features
   │          ▼
   │      [Formatter → PDF → Publish to R2]
   │          ▼
   │   [Notify Admin]   ← emails the admin a preview + one-tap review links
   │          ▼
   │      [Approval]    ← pauses here (LangGraph interrupt) until the admin decides
   │          │
   │   request_changes  │  approve
   └──────────┘         ▼
                     [Send]   ← delivers to every active subscriber, skips already-sent
                        │
                       END
```

Approval is a **real graph node**, not a side script: the admin's decision resumes the paused
graph directly, so "request changes" is a genuine loop back to the editor with feedback injected
into its prompt, and the whole exchange is traced end-to-end in Langfuse.

### Agent & Node Roles

| Component | File | What it does |
|---|---|---|
| **Paper Agent** | `agents/paper_agent.py` | Fetches papers from ArXiv (`cs.AI`, `cs.LG`, `cs.CL`, `stat.ML`) and Papers With Code |
| **Model Watcher** | `agents/model_watcher.py` | Monitors RSS feeds from OpenAI, Anthropic, Google, Meta, HuggingFace, Mistral, Cohere |
| **GitHub Tracker** | `agents/github_tracker.py` | Scrapes GitHub Trending + fetches new releases from watched repos |
| **News Agent** | `agents/news_agent.py` | Parses RSS feeds and community sources configured in `config/sources.yaml` |
| **Framework Doc Agent** | `agents/framework_doc_agent.py` | Monitors LangChain, LangGraph, CrewAI, vLLM, Ollama, NeMo, and more for new releases |
| **Preselector** | `agents/preselector.py` | Deterministically dedupes and scores every item before any LLM call, applying per-category limits and per-source diversity caps |
| **Summarizer** | `agents/summarizer.py` | Groq call per selected item → summary, why_it_matters, key_takeaway, difficulty (cached by content hash); a failed call falls back to a cleaned, Markdown-stripped excerpt — never raw changelog syntax |
| **Editor** | `agents/editor.py` | Two independent Groq calls: a **core** call for must-have content (TL;DR, Paper of the Week, Tool of the Week) and a separate **extras** call (Research Radar, Emerging Patterns, Production Playbook, Under the Radar, Quick Hits, Trending/Glossary/Learning) — a failure in one never blanks out the other. Extras are built from already-collected items that didn't make each category's top-N cut, at no extra Groq cost. Incorporates admin feedback into the core call on a revision. |
| **Formatter / PDF** | `formatter/` | Jinja2 renders the newspaper, WeasyPrint converts it to PDF |
| **Publisher** | `storage/artifact_service.py` + `storage/r2_client.py` | Uploads HTML/PDF to a private R2 bucket, reconciling instead of blindly re-uploading |
| **Notify Admin** | `graph/pipeline.py::node_notify_admin` | Emails the admin a preview with one-tap review buttons (when the API is deployed) |
| **Approval** | `graph/pipeline.py::node_approval` | Pauses the graph (`interrupt()`) until the admin resumes it with a decision |
| **Send** | `graph/pipeline.py::node_send` | Delivers to every active subscriber via `delivery/broadcast.py`, skipping anyone already delivered |
| **Review entry point** | `graph/review.py` | Resumes the paused graph with the admin's decision (`Command(resume=...)`); the same function backs the CLI, GitHub Actions, and the API |
| **Review/Subscriber API** | `api/` | FastAPI service: signed one-tap approve/reject links, public subscribe page, tokenized unsubscribe |
| **Email transport** | `delivery/transport.py` | Swappable `EmailTransport` interface (only Gmail SMTP implemented today) |
| **Pipeline** | `graph/pipeline.py` | LangGraph `StateGraph`, checkpointed to PostgreSQL per ISO week |
| **Scheduler (GitHub Actions)** | `.github/workflows/weekly-newsletter.yml` | Sunday 8 AM IST cron that generates and notifies the admin |
| **Scheduler (local, alternative)** | `scheduler/runner.py` | APScheduler alternative if you'd rather run it yourself than via CI |

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
│   └── editor.py               # Groq curation + features, revision-aware
├── formatter/
│   ├── formatter.py            # Jinja2 HTML renderer
│   ├── pdf_generator.py        # HTML → PDF via WeasyPrint
│   └── templates/newspaper.html
├── graph/
│   ├── pipeline.py             # LangGraph StateGraph: generate → approval → send
│   └── review.py               # Resumes the paused graph with the admin's decision
├── database/
│   ├── connection.py           # PostgreSQL connection boundary
│   ├── migrate.py              # Schema migrator
│   ├── checkpointer.py         # LangGraph PostgresSaver wrapper
│   ├── summary_repository.py   # Content-hash keyed summary cache
│   ├── workflow_repository.py  # Issues/workflow-run tracking + latest-sent lookup
│   ├── artifact_repository.py  # R2 artifact bookkeeping
│   ├── review_repository.py    # Approval audit trail + per-subscriber delivery status
│   ├── subscriber_repository.py# Subscriber CRUD (+ CLI)
│   └── migrations/*.sql
├── storage/
│   ├── r2_client.py            # Cloudflare R2 client + presigned URLs
│   └── artifact_service.py     # Reconcile-before-reupload publishing logic
├── llm/
│   └── groq_client.py          # Rate-limit-aware Groq request gateway
├── delivery/
│   ├── transport.py            # Swappable EmailTransport (Gmail SMTP today)
│   ├── email_sender.py         # Admin review, subscriber, and welcome emails
│   └── broadcast.py            # Sends to every active, not-yet-delivered subscriber
├── api/
│   ├── main.py                 # FastAPI app
│   ├── security.py             # Signed tokens for one-tap review/unsubscribe links
│   └── routers/
│       ├── review.py           # Approve / request-changes confirmation + action endpoints
│       └── subscribers.py      # Public subscribe page + JSON API, unsubscribe
├── scheduler/
│   └── runner.py                # APScheduler local-runner alternative to GitHub Actions
├── config/
│   └── sources.yaml            # Data sources, repos, RSS feeds, preselection weights
├── .github/workflows/
│   ├── weekly-newsletter.yml   # Sunday 8 AM IST cron: generate + notify admin
│   ├── review-newsletter.yml   # Manual: apply an approve/request-changes decision
│   └── ci.yml                  # Runs the full test suite on every push/PR
├── render.yaml                  # Render Blueprint for deploying api/
├── observability.py             # Langfuse + Groq instrumentation
├── output/                      # Generated HTML + PDF files (auto-created)
├── tests/                       # Unit tests (`python -m unittest discover tests`)
├── .env.example                 # Template for secrets
├── requirements.txt
└── main.py                      # Run once manually (`--dry-run` skips the admin email)
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

### 3. Get your API keys and services

| Key | Where to get it | Cost |
|---|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | Free tier available |
| `DATABASE_URL` | Any PostgreSQL provider (e.g. Neon, Supabase, local Postgres) | Free tier available |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET_NAME` | Cloudflare dashboard → R2 → create a bucket + API token | Free tier available |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | [cloud.langfuse.com](https://cloud.langfuse.com) | Free tier available |
| `GITHUB_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) → Generate new token (classic) → no scopes needed | Free |
| Gmail App Password | Google Account → Security → 2-Step Verification → App passwords | Free |
| `ADMIN_EMAIL` | Your own inbox — receives the draft for review | Free |
| `API_SIGNING_SECRET` | Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` | Free |

### 4. Configure your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in the values described in `.env.example`.

### 5. Initialize the database once

```bash
python -m database.checkpointer
python -m database.migrate
```

### 6. Test it once

```bash
python main.py --dry-run
```

Runs the full pipeline, generates HTML + PDF, uploads to R2, and skips emailing anyone. Run
without `--dry-run` once you're ready for it to actually email the admin for real.

### 7. Add subscribers

Either via the CLI:
```bash
python -m database.subscriber_repository add someone@example.com
```
or once the API is deployed (step 8), point people at `https://<your-render-url>/subscribe` —
a self-serve signup page that also emails a welcome message with a link to the latest issue.

### 8. Deploy the review/subscriber API (optional, but needed for one-tap buttons)

```bash
git push   # Render auto-deploys from render.yaml once the service is connected
```

On [render.com](https://render.com), create a **Web Service** from this repo — Render should
detect `render.yaml` and pre-fill the build/start commands. Set every env var it lists (same
`GROQ_*`/`DATABASE_URL`/`R2_*`/`EMAIL_*`/`ADMIN_EMAIL` as above, plus `API_SIGNING_SECRET`), then
once deployed, add the assigned URL as `API_BASE_URL` in both Render's env vars **and** your
local `.env` / GitHub Actions repo variables. Without `API_BASE_URL` set, admin emails fall back
to plain-text instructions instead of clickable buttons — nothing breaks, it's just less
convenient.

### 9. Automate it

`.github/workflows/weekly-newsletter.yml` runs on GitHub's own Sunday 8 AM IST cron. Add the
required secrets/variables in your repo settings (**Settings → Secrets and variables →
Actions**) — everything in the table above, plus `API_BASE_URL`/`API_SIGNING_SECRET` if you
deployed the API. Once set, it runs unattended.

If you'd rather run it continuously on your own machine instead of via CI, use the APScheduler
alternative (`python scheduler/runner.py`, configured via `SCHEDULE_DAY`/`HOUR`/`MINUTE` in
`.env`) — but note this only triggers *generation*, review still works the same way.

---

## Human-in-the-Loop Review

1. **Generate** — the pipeline runs, publishes HTML/PDF to R2, and emails the admin a preview.
   The issue is now paused, awaiting a decision — nothing has gone to subscribers yet.
2. **Decide** — the admin approves or requests changes, via whichever is convenient:
   - Tap **Approve**/**Request Changes** in the email (needs the API deployed, step 8 above)
   - Run the **"Review newsletter"** GitHub Actions workflow manually (`issue_key`, `decision`,
     optional `feedback`)
   - `python -m graph.review --issue-key 2026-W29 --decision approve`
3. **Approve** → delivers to every active subscriber (`delivery/broadcast.py`), skipping anyone
   already delivered this issue — safe to re-run if a send partially fails.
4. **Request changes** (feedback required) → re-runs just the editor with that feedback folded
   into its prompt, regenerates HTML/PDF/publish, and emails the admin a new revision. Loops back
   to step 2.

None of this depends on any process staying alive between steps — the paused graph state lives
in PostgreSQL (via LangGraph's checkpointer), so review can happen minutes or weeks later, from
any machine, with no timeout.

---

## Subscribers

- **Sign up**: `https://<your-render-url>/subscribe` (public, no login) or
  `python -m database.subscriber_repository add/remove/list <email>` (admin CLI).
- **Welcome email**: sent immediately on signup, with a temporary signed link
  (`storage/r2_client.py::generate_presigned_url`) to the most recently sent issue, if one
  exists.
- **Unsubscribe**: a unique link in every email footer — no login needed, self-service.
- **Delivery is idempotent**: `email_deliveries` records each subscriber's outcome per issue, so
  re-approving after a partial failure only retries whoever didn't get through.

---

## How the LangGraph Pipeline Works

LangGraph treats the newspaper as a **state machine with a human-in-the-loop cycle**:

```
collect → preselect → summarize → edit → format → pdf → publish → notify_admin → approval
                          ▲                                                          │
                          └──────────────────── request_changes ─────────────────────┤
                                                                                approve │
                                                                                        ▼
                                                                                      send → END
```

(`--dry-run` ends right after `publish`, skipping `notify_admin`/`approval`/`send` entirely.)

`approval` uses LangGraph's `interrupt()` — the graph genuinely pauses there, checkpointed to
PostgreSQL, until `graph/review.py` resumes it with `Command(resume={"decision": ..., "feedback":
...})`. The `collect` node still runs all 5 data agents in **parallel threads**. A completed
week's run is reused rather than regenerated; the summary cache further skips re-summarizing
unchanged items across revisions.

Visualise the graph:

```python
from graph.pipeline import build_pipeline
print(build_pipeline().get_graph().draw_ascii())
```

---

## Cost Estimate

| Item | Cost |
|---|---|
| Groq API (run, ~20-30 items) | Free tier covers typical usage |
| PostgreSQL (Neon/Supabase free tier) | Free |
| Cloudflare R2 storage | Free tier covers typical usage |
| Langfuse observability | Free tier |
| Render (API service) | Free tier (spins down when idle, ~50s cold start) |
| GitHub Actions minutes | Free tier covers a weekly run comfortably |
| Gmail SMTP, GitHub API, ArXiv/RSS | Free |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `[Error] Missing environment variables: ...` | Make sure `.env` includes `GROQ_API_KEY`, `DATABASE_URL`, all `R2_*` keys, and (outside `--dry-run`) `EMAIL_SENDER`/`EMAIL_PASSWORD`/`ADMIN_EMAIL` |
| Admin email has no clickable buttons | Set `API_BASE_URL` in `.env` (and deploy the API — see Setup step 8) |
| `[Review] Issue ... is not awaiting review` | The graph isn't paused at `approval` for that issue — check `python -m graph.review` was pointed at the right `issue_key`, or that it hasn't already been approved |
| Gmail authentication failed | Use an **App Password**, not your regular Gmail password. Enable 2FA first. |
| WeasyPrint install error | Install system Pango libraries |
| GitHub API rate limit | Add `GITHUB_TOKEN` to `.env` (raises limit from 60 to 5000 req/hour) |
| PDF is blank/broken | Some WeasyPrint versions need `libpangoft2`. Run `sudo apt install libpangoft2-1.0-0` |
| `[Database] Connection failed` | Check `DATABASE_URL` and run `python -m database.migrate` again |
| `[R2] Connection failed` | Check the `R2_*` credentials and that the bucket exists |
| Render request takes ~50s | Free-tier instance spun down from inactivity — normal, only affects the first request |

---

## Learning Resources

Since this project is built for learning, here's what each component teaches:

| Component | Concepts you learn |
|---|---|
| `agents/preselector.py` | Deterministic scoring/ranking, dedup heuristics, diversity constraints |
| `agents/summarizer.py` | Prompt engineering, Groq API, JSON structured output, content-hash caching, graceful-degradation fallback design |
| `agents/editor.py` | Multi-step LLM reasoning, feedback-conditioned regeneration, splitting calls to isolate blast radius on failure |
| `graph/pipeline.py` | LangGraph StateGraph, cycles, `interrupt()`/`Command` human-in-the-loop |
| `graph/review.py` | Resuming a paused graph safely, idempotent retry design |
| `database/` | PostgreSQL schema design, migrations, LangGraph checkpointer integration |
| `storage/` | S3-compatible object storage, presigned URLs, idempotent publish/reconcile |
| `delivery/transport.py` | Interface design for swappable infrastructure (email provider) |
| `api/` | FastAPI, signed tokens for stateless auth, GET-shows-confirm/POST-mutates safety pattern |
| `llm/groq_client.py` | Rate limiting, exponential backoff, quota handling |
| `observability.py` | LLM tracing with Langfuse |
| `.github/workflows/` | Scheduled + manual + CI GitHub Actions workflows |
