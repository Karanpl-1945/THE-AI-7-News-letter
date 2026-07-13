# ⚡ THE AI 7 — Your Weekly AI Intelligence Brief

A fully automated weekly AI newspaper delivered to your inbox every Sunday, covering the latest in AI research, model releases, GitHub trends, and framework updates — powered by **Claude** and **LangGraph**.

---

## What You Get

Every Sunday morning, a beautifully formatted newspaper lands in your inbox (HTML + PDF) with:

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

```
[APScheduler — Every Sunday]
         │
         ▼
[Orchestrator — LangGraph Pipeline]
         │
   ┌─────┼──────────────────────────────┐
   ▼     ▼          ▼          ▼        ▼
Paper  Model     GitHub     News    Framework
Agent  Watcher   Tracker    Agent   Doc Agent
   └─────┼──────────────────────────────┘
         │  (parallel threads)
         ▼
[Summarizer Agent]  ← Claude enriches each item
         │
         ▼
[Editor Agent]      ← Claude curates, ranks, writes features
         │
         ▼
[Formatter]         ← Jinja2 renders HTML newspaper
         │
         ▼
[PDF Generator]     ← WeasyPrint converts HTML → PDF
         │
         ▼
[Email Delivery]    ← Gmail SMTP sends to your inbox
```

### Agent Roles

| Agent | File | What it does |
|---|---|---|
| **Paper Agent** | `agents/paper_agent.py` | Fetches papers from ArXiv (`cs.AI`, `cs.LG`, `cs.CL`, `stat.ML`) and Papers With Code |
| **Model Watcher** | `agents/model_watcher.py` | Monitors RSS feeds from OpenAI, Anthropic, Google, Meta, HuggingFace, Mistral |
| **GitHub Tracker** | `agents/github_tracker.py` | Scrapes GitHub Trending + fetches new releases from watched repos |
| **News Agent** | `agents/news_agent.py` | Parses RSS from The Batch, Import AI, MIT Tech Review, Reddit r/MachineLearning |
| **Framework Doc Agent** | `agents/framework_doc_agent.py` | Monitors LangChain, LangGraph, CrewAI, vLLM, Ollama, NeMo, and more for new releases |
| **Summarizer** | `agents/summarizer.py` | Claude call per item → adds summary, why_it_matters, key_takeaway, difficulty |
| **Editor** | `agents/editor.py` | Claude selects top stories, writes TL;DR, Paper of Week, Tool of Week, Glossary |
| **Formatter** | `formatter/formatter.py` | Jinja2 renders `newspaper.html` template with all curated content |
| **PDF Generator** | `formatter/pdf_generator.py` | WeasyPrint converts HTML → PDF and saves to `output/` |
| **Email Sender** | `delivery/email_sender.py` | Gmail SMTP sends HTML body + PDF attachment |
| **Pipeline** | `graph/pipeline.py` | LangGraph StateGraph connecting all nodes in sequence |
| **Scheduler** | `scheduler/runner.py` | APScheduler runs the pipeline every Sunday at configured time |

---

## Project Structure

```
ai-newspaper/
├── agents/
│   ├── paper_agent.py          # ArXiv + Papers With Code
│   ├── model_watcher.py        # AI company blog RSS feeds
│   ├── github_tracker.py       # GitHub Trending + release watcher
│   ├── news_agent.py           # AI news RSS + Reddit
│   ├── framework_doc_agent.py  # Framework release monitor
│   ├── summarizer.py           # Claude enrichment per item
│   └── editor.py               # Claude curation + features
├── formatter/
│   ├── formatter.py            # Jinja2 HTML renderer
│   ├── pdf_generator.py        # HTML → PDF via WeasyPrint
│   └── templates/
│       └── newspaper.html      # Newspaper template (CSS + Jinja2)
├── graph/
│   └── pipeline.py             # LangGraph StateGraph
├── delivery/
│   └── email_sender.py         # Gmail SMTP delivery
├── scheduler/
│   └── runner.py               # APScheduler weekly trigger
├── config/
│   └── sources.yaml            # All data sources, repos, RSS feeds
├── output/                     # Generated HTML + PDF files (auto-created)
├── .env.example                # Template for secrets
├── requirements.txt
└── main.py                     # Run once manually
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

### 4. Get your API keys

| Key | Where to get it | Cost |
|---|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | ~₹35/month for weekly runs |
| `GITHUB_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) → Generate new token (classic) → no scopes needed | Free |
| Gmail App Password | Google Account → Security → 2-Step Verification → App passwords | Free |

### 5. Configure your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
EMAIL_SENDER=yourgmail@gmail.com
EMAIL_PASSWORD=xxxx xxxx xxxx xxxx    # 16-character App Password
EMAIL_RECIPIENT=yourgmail@gmail.com

USER_NAME=Your Name
USER_INTERESTS=LLMs,agents,computer vision
SKILL_LEVEL=intermediate              # beginner | intermediate | advanced

SCHEDULE_DAY=sunday
SCHEDULE_HOUR=8
SCHEDULE_MINUTE=0
```

### 6. Test it once

```bash
python main.py
```

This runs the full pipeline immediately and sends one newspaper to your inbox.
Check the `output/` folder for the saved HTML and PDF files.

### 7. Start the weekly automation

```bash
python scheduler/runner.py
```

Leave this running in the background. It will automatically trigger every Sunday at your configured time.

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

Claude's summariser and editor will adapt their language and selections accordingly.

### Change delivery day/time

```env
SCHEDULE_DAY=saturday
SCHEDULE_HOUR=9
SCHEDULE_MINUTE=30
```

---

## How the LangGraph Pipeline Works

LangGraph treats the newspaper as a **state machine**. Each node is a Python function that receives the full state dictionary, does its work, and returns an updated state. The state flows through nodes in sequence:

```
collect → summarize → edit → format → pdf → email → END
```

The `collect` node runs all 5 data agents in **parallel threads** using `concurrent.futures`, so fetching takes the time of the slowest agent, not the sum of all agents.

You can visualise the graph by adding this to `graph/pipeline.py`:

```python
pipeline = build_pipeline()
print(pipeline.get_graph().draw_ascii())
```

---

## Cost Estimate

| Item | Cost |
|---|---|
| Claude API (weekly run, ~20-30 items) | ~$0.05–0.15 per run |
| **Monthly (4 runs)** | **~$0.20–0.60 / month** |
| GitHub API | Free |
| ArXiv, RSS, Papers With Code | Free |
| Gmail SMTP | Free |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `EMAIL_SENDER or EMAIL_PASSWORD not set` | Make sure `.env` file exists and `load_dotenv()` ran |
| Gmail authentication failed | Use an **App Password**, not your regular Gmail password. Enable 2FA first. |
| WeasyPrint install error | Install system Pango libraries (see Step 3 above) |
| GitHub API rate limit | Add `GITHUB_TOKEN` to `.env` (raises limit from 60 to 5000 req/hour) |
| No papers found | Check your internet connection; ArXiv may be temporarily slow |
| PDF is blank/broken | Some WeasyPrint versions need `libpangoft2`. Run `sudo apt install libpangoft2-1.0-0` |

---

## Learning Resources

Since this project is built for learning, here's what each component teaches:

| Component | Concepts you learn |
|---|---|
| `agents/paper_agent.py` | Working with APIs, data parsing, deduplication |
| `agents/summarizer.py` | Prompt engineering, Claude API, JSON structured output |
| `agents/editor.py` | Multi-step LLM reasoning, chained prompts |
| `graph/pipeline.py` | LangGraph StateGraph, typed state, agent orchestration |
| `formatter/templates/newspaper.html` | Jinja2 templating, CSS layout, print-friendly design |
| `delivery/email_sender.py` | MIME email, SMTP, file attachments |
| `scheduler/runner.py` | APScheduler, cron triggers, background automation |
