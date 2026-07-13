# Autonomous AI Intelligence Newsletter Platform
## Complete Project Plan, Architecture, Implementation Roadmap, Risk Guide, and Placement Preparation

**Working project title:** Autonomous AI Intelligence Newsletter Platform  
**Alternative titles:** AI Trends Intelligence Engine, Automated AI Research Digest, AI Signal Weekly  
**Primary goal:** Build a production-style, low-cost, cloud-automated system that discovers important AI developments, ranks and summarizes them, generates an HTML/PDF newsletter, supports human approval, archives every issue, and sends it reliably to subscribers.

> This project should be presented as an **AI automation, backend engineering, and workflow orchestration system**, not merely as a newsletter generator.

---

# 1. Problem Statement

Artificial intelligence information is spread across many sources:

- Research-paper platforms such as arXiv and Semantic Scholar
- GitHub repositories and releases
- Hugging Face models, datasets, and papers
- Official company and framework blogs
- RSS feeds and technical publications
- Community discussions and developer feedback
- Model, tool, benchmark, and framework announcements

A person interested in AI must manually open many websites, identify relevant updates, remove repeated stories, judge credibility, read long content, and create a concise weekly summary. Existing newsletters already solve parts of this problem, but the purpose of this project is different.

The engineering problem is:

> How can we build a reliable, low-cost, cloud-based AI intelligence pipeline that automatically collects multi-source content, identifies high-value developments, avoids duplication, produces evidence-linked summaries, supports automated and human quality checks, archives every issue, and sends each approved issue safely to subscribers?

The system must also work without requiring the developer’s laptop to remain switched on.

---

# 2. Project Objective

The project should achieve the following objectives:

1. Collect AI-related updates from several APIs and RSS feeds.
2. Normalize content from different sources into a common structure.
3. Filter outdated, irrelevant, low-quality, and duplicate items.
4. Rank stories using transparent signals rather than only LLM judgment.
5. Use Grok or another LLM to summarize shortlisted content.
6. Preserve source links and avoid unsupported claims.
7. Run an automated quality-review stage.
8. Allow a human reviewer to approve, reject, or request revisions.
9. Generate professional HTML and PDF editions.
10. Archive every generated and sent issue.
11. Store subscribers and delivery records securely.
12. Prevent duplicate sending during retries.
13. Persist workflow state so interrupted processing can resume.
14. Run automatically through cloud infrastructure.
15. Remain within free tiers during the MVP whenever possible.
16. Provide metrics, logs, documentation, and tests suitable for placement interviews.

---

# 3. Scope

## 3.1 MVP scope

The first usable version should include:

- arXiv collector
- GitHub repository/release collector
- RSS collector for selected official AI blogs
- Rule-based filtering
- Exact and fuzzy duplicate removal
- Basic ranking
- Grok summarization
- Source citations
- HTML newsletter generation
- PDF generation
- PostgreSQL persistence
- Manual GitHub Actions trigger
- Weekly scheduled trigger
- Human approval before public sending
- Sending to a small verified subscriber list
- Newsletter archive
- Per-recipient delivery logs

## 3.2 Out of scope for the first version

Avoid building these initially:

- Hundreds of sources
- Fully autonomous publishing without review
- Complex multi-agent architecture
- Recommendation personalization for every subscriber
- Mobile application
- Real-time news delivery
- Large-scale scraping infrastructure
- Thousands of subscribers
- Advanced payment or subscription plans
- Full marketing analytics platform
- Training a custom language model

These can become later extensions.

---

# 4. Proposed Solution

The platform follows this high-level flow:

```text
GitHub Actions schedule/manual trigger
                |
                v
        Start generation run
                |
                v
  Collect content from multiple sources
                |
                v
 Normalize and validate source records
                |
                v
 Filter by time, topic, quality, and language
                |
                v
 Exact + semantic/fuzzy deduplication
                |
                v
 Rank shortlisted stories
                |
                v
 Generate structured summaries with Grok
                |
                v
 Automated fact/quality review
          /                 \
       Passed              Failed
         |                    |
         v                    v
 Generate HTML/PDF      Revise or retry
         |
         v
 Save draft + archive files
         |
         v
 Human review and approval
      /          |           \
 Approve    Request changes   Reject
    |              |             |
    v              v             v
Send workflow   Revision      End/Archive
    |
    v
Create recipient delivery records
    |
    v
Send individually in safe batches
    |
    v
Record sent/failed/bounced results
    |
    v
Issue marked as sent
```

---

# 5. Why LangGraph Is Used

A normal Python pipeline is sufficient for deterministic operations such as collecting feeds, normalizing records, calculating scores, and rendering templates.

LangGraph should be used only where the workflow becomes stateful or conditional:

- Quality-check routing
- Revision loops
- Retry limits
- Human-in-the-loop approval
- Pausing and resuming
- Checkpoint recovery
- Tracking the current node
- Fault-tolerant execution

LangGraph checkpointers save graph state at execution steps and support fault tolerance and human-in-the-loop workflows. For production persistence, the state must be stored outside the temporary GitHub runner.

A good design principle is:

> Use regular Python for deterministic processing and LangGraph for decisions, loops, pauses, and recovery.

---

# 6. Recommended Technology Stack

## 6.1 Core stack

| Purpose | Recommended technology | Reason |
|---|---|---|
| Programming language | Python 3.12 | Strong API, data, AI, and automation ecosystem |
| API/backend | FastAPI | Future admin dashboard and approval endpoints |
| Workflow orchestration | LangGraph | Conditional routing, checkpoints, HITL |
| Main database | PostgreSQL on Neon | Relational integrity plus JSONB and free serverless tier |
| ORM | SQLAlchemy 2.x | Clean models and database abstraction |
| Migrations | Alembic | Version-controlled schema evolution |
| File storage | Cloudflare R2 | S3-compatible storage with generous free tier |
| LLM | Grok via xAI API | User-selected summarization/editorial model |
| Templates | Jinja2 | Generate HTML from structured issue data |
| PDF generation | Playwright | Browser-quality HTML-to-PDF rendering |
| Email provider | Resend | Simple API and free small-volume tier |
| Scheduling/compute | GitHub Actions | Laptop-free weekly execution |
| Logging | Python structured logging | Free and sufficient initially |
| Testing | pytest | Unit and integration testing |
| Data validation | Pydantic | Strong input/output schemas |
| HTTP client | httpx | Async requests, timeout support |
| Retry library | tenacity | Exponential backoff and retry policies |
| Code quality | Ruff + mypy | Linting, formatting, and type checks |
| Packaging | uv or pip | Dependency management |
| Containers | Docker | Reproducible local development |

---

# 7. Cloud Platform Choices

## 7.1 GitHub Actions — scheduler and short-lived compute

### Purpose

- Trigger generation weekly
- Trigger generation manually
- Run tests
- Install dependencies
- Execute the pipeline
- Trigger the send workflow after approval
- Store logs and temporary artifacts

### Why it fits

The workflow runs only periodically. A permanently running VM would be unnecessary during the MVP. GitHub Actions can run standard hosted runners free for public repositories; private repositories receive included minutes according to the account plan.

### Important cautions

- Scheduled runs may be delayed.
- Avoid scheduling exactly at minute `00`.
- Scheduled workflows execute from the default branch.
- Include `workflow_dispatch` for manual recovery.
- GitHub-hosted runners are temporary.
- Never depend on local runner files for persistence.
- Pin third-party Actions to trusted versions.
- Keep secrets in GitHub Secrets.
- Add concurrency control to prevent two issue-generation runs from overlapping.

### Suggested schedule

```yaml
on:
  schedule:
    - cron: "17 8 * * 0"
      timezone: "Asia/Kolkata"
  workflow_dispatch:
```

Use an unusual minute such as `17` to reduce peak-hour scheduling contention.

---

## 7.2 Neon PostgreSQL — structured database and checkpoint persistence

### Purpose

Store:

- Subscribers
- Articles
- Source metadata
- Newsletter issues
- Newsletter-article relationships
- Workflow runs
- Approval decisions
- Delivery records
- Prompt versions
- Cost/usage records
- LangGraph checkpoints

### Why Neon

As of July 2026, Neon’s free plan advertises 0.5 GB storage per project and 100 compute-unit hours per project per month. This is appropriate for a small, mostly idle, weekly automation workload.

### Why PostgreSQL

The important entities are relational:

```text
Subscriber -> Delivery -> Newsletter Issue
Newsletter Issue -> Newsletter Article -> Article
Newsletter Issue -> Workflow Run -> Workflow Events
Workflow Run -> Approval Decision
```

PostgreSQL provides:

- Foreign keys
- Unique constraints
- Transactions
- SQL joins
- Indexes
- JSONB for flexible LLM output
- Mature Python support
- Good compatibility with LangGraph persistence

### Cautions

- The free storage limit is relatively small.
- Do not store PDFs, images, or full research papers in PostgreSQL.
- Do not save every raw API response forever.
- Keep checkpoint state small.
- Add data-retention policies.
- Monitor database size monthly.
- Use connection pooling appropriately with serverless Postgres.
- Avoid opening a new database connection for every article.

---

## 7.3 Cloudflare R2 — object storage

### Purpose

Store:

- HTML issues
- PDF issues
- Newsletter images
- Generated charts
- Optional raw-source snapshots
- Backup exports

### Why R2

As of May 2026, the official free tier includes 10 GB-month of Standard storage, one million Class A operations, ten million Class B operations, and free internet egress for supported usage.

### Recommended key structure

```text
ai-newsletter/
  issues/
    2026/
      issue-001/
        newsletter.html
        newsletter.pdf
        metadata.json
      issue-002/
        newsletter.html
        newsletter.pdf
  assets/
    logo.svg
    default-cover.webp
  exports/
    database-backup-2026-07.sql.gz
```

### Cautions

- Keep the bucket private unless public links are intentionally required.
- Use signed URLs for private previews.
- Store object keys in PostgreSQL, not only temporary URLs.
- Add lifecycle policies for unnecessary raw files.
- Validate uploads using size and checksum.
- Never expose R2 secret keys in frontend code.

---

## 7.4 Resend — email delivery

### Purpose

- Send individual newsletter emails
- Return provider message IDs
- Support domain authentication
- Receive webhook events for delivery/bounce status
- Send verification and unsubscribe messages

### Free-tier use

The current public pricing lists 3,000 emails per month on the free tier. Historically, the free transactional tier has also applied a 100-email daily limit, so current account limits must be confirmed before launch.

### Cautions

- Buy and verify a custom domain before public launch.
- Configure SPF, DKIM, and DMARC.
- Do not place all users in `To` or `CC`.
- Send individually or through a proper audience/broadcast mechanism.
- Process bounce and complaint events.
- Immediately stop sending to unsubscribed or hard-bounced users.
- Add an unsubscribe link to every newsletter.
- Use a `Reply-To` address that someone checks.
- Avoid attaching large PDFs; include a hosted link instead.

---

## 7.5 Grok/xAI API — summarization and editorial intelligence

### Purpose

- Categorize shortlisted stories
- Generate concise, structured summaries
- Explain why a story matters
- Create final editorial transitions
- Review issue quality
- Suggest revisions

### Do not use Grok for everything

Use official APIs and deterministic rules first. Grok should process only shortlisted, relevant content.

Bad approach:

```text
Fetch 1,000 articles -> send all text to Grok
```

Better approach:

```text
Fetch 1,000 items
-> date/source filters
-> remove obvious duplicates
-> calculate metadata score
-> shortlist 30
-> send selected evidence to Grok
-> choose 10–15 final items
```

### Cautions

- xAI API usage is token-priced.
- Apply strict input limits.
- Track tokens and estimated cost.
- Cache summaries using content hashes.
- Use structured output.
- Set rate-limit-aware concurrency.
- Do not trust generated claims without source evidence.
- Require source URLs for every published story.
- Reject summaries that introduce unsupported numbers or names.
- Limit retry loops.

---

# 8. Database Design

Use one PostgreSQL database with logically separated tables or schemas.

## 8.1 Main entities

### `subscribers`

```text
id
name
email
status
verification_token_hash
unsubscribe_token_hash
subscribed_at
verified_at
unsubscribed_at
created_at
updated_at
```

Statuses:

```text
pending
active
unsubscribed
bounced
blocked
```

### `sources`

```text
id
name
source_type
base_url
enabled
credibility_weight
fetch_interval
last_success_at
last_failure_at
config_json
```

### `articles`

```text
id
source_id
external_id
title
canonical_url
authors
published_at
raw_excerpt
normalized_text
content_hash
category
language
metadata_json
created_at
updated_at
```

### `article_metrics`

Useful for changing signals:

```text
id
article_id
captured_at
stars
forks
watchers
downloads
citations
comments
score_components_json
```

### `newsletter_issues`

```text
id
issue_number
title
slug
period_start
period_end
status
summary
html_object_key
pdf_object_key
generated_at
approved_at
sent_at
created_at
updated_at
```

Statuses:

```text
draft
reviewing
changes_requested
approved
sending
sent
failed
archived
```

### `newsletter_articles`

```text
newsletter_id
article_id
section_name
display_order
ranking_score
final_summary
why_it_matters
limitations
source_citations_json
```

### `workflow_runs`

```text
id
newsletter_id
thread_id
workflow_name
status
current_node
retry_count
started_at
updated_at
completed_at
error_code
error_message
metadata_json
```

### `workflow_events`

```text
id
workflow_run_id
node_name
event_type
attempt_number
duration_ms
input_summary_json
output_summary_json
error_message
created_at
```

### `approvals`

```text
id
newsletter_id
workflow_run_id
reviewer_id
decision
comments
reviewed_at
```

### `email_deliveries`

```text
id
newsletter_id
subscriber_id
provider_message_id
status
attempt_count
sent_at
delivered_at
opened_at
clicked_at
bounced_at
error_code
error_message
created_at
updated_at
```

Critical constraint:

```sql
UNIQUE (newsletter_id, subscriber_id)
```

This is essential for idempotency.

### `prompt_versions`

```text
id
name
version
prompt_template
model_name
temperature
active
created_at
```

### `llm_usage`

```text
id
workflow_run_id
article_id
operation
model_name
input_tokens
output_tokens
estimated_cost
latency_ms
created_at
```

---

# 9. Data Storage Strategy

## Store in PostgreSQL

- IDs and relationships
- Subscriber data
- Article metadata
- Short normalized excerpts
- Rankings and scores
- Final summaries
- Workflow status
- Approval status
- Delivery status
- LLM usage statistics
- Object-storage keys

## Store in R2

- HTML files
- PDF files
- Images
- Large raw-source snapshots
- Database export backups
- Optional issue metadata JSON

## Do not store permanently unless required

- Complete scraped webpages
- Entire research papers
- Repeated unchanged API payloads
- Large model prompts
- Full LangGraph state containing all raw content
- Temporary browser/PDF files

---

# 10. Content Sources

Begin with a small, high-quality source list.

## 10.1 Research

- arXiv API
- Semantic Scholar API
- Papers With Code, where API/use terms permit
- Hugging Face Daily Papers
- Conference proceedings or official feeds

## 10.2 Open-source projects

- GitHub REST API
- GitHub GraphQL API
- GitHub Releases
- Repository topics
- Star, fork, contributor, issue, and release signals

## 10.3 Official AI sources

- OpenAI official updates
- xAI official updates
- Anthropic official updates
- Google DeepMind official updates
- Meta AI official updates
- Microsoft Research
- NVIDIA technical blogs
- Hugging Face
- LangChain/LangGraph
- LlamaIndex
- PyTorch
- TensorFlow
- vLLM

## 10.4 Community signals

Use carefully:

- Hacker News
- Reddit
- GitHub issues/discussions
- Public developer forums
- X content only when API access and terms allow

Community feedback must be labeled as opinion or discussion, not verified fact.

---

# 11. Common Article Schema

Every collector should output the same internal schema:

```python
class CollectedItem(BaseModel):
    source_name: str
    source_type: str
    external_id: str | None
    title: str
    canonical_url: str
    published_at: datetime
    authors: list[str] = []
    excerpt: str
    raw_metadata: dict
    fetched_at: datetime
```

Later processing enriches it:

```python
class ProcessedItem(CollectedItem):
    content_hash: str
    category: str
    relevance_score: float
    quality_score: float
    novelty_score: float
    final_score: float
    duplicate_of: str | None = None
```

---

# 12. Ranking System

Do not let the LLM make the entire ranking decision.

## 12.1 Possible signals

### General signals

- Recency
- Source credibility
- Topic relevance
- Novelty
- Practical usefulness
- Evidence availability
- Community attention
- Cross-source confirmation
- Code/data availability

### GitHub signals

- Stars gained during the week
- Fork growth
- Contributor growth
- Commit activity
- New release
- Issue/discussion activity
- Repository age
- Documentation quality
- License availability

### Research signals

- Code availability
- Dataset availability
- Institution/author credibility
- Benchmark improvement
- Reproducibility information
- Community discussion
- Citation velocity when available
- Practical significance

## 12.2 Example scoring formula

```text
final_score =
    0.20 * relevance
  + 0.15 * recency
  + 0.15 * source_credibility
  + 0.15 * novelty
  + 0.15 * community_signal
  + 0.10 * practical_value
  + 0.10 * evidence_quality
```

Weights should be stored in configuration so they can be changed without editing code.

## 12.3 Evaluation

Create a small labeled dataset:

```text
item_id
human_relevance_score
human_priority_rank
include_or_exclude
reason
```

Measure:

- Precision@K
- Recall@K
- NDCG@K
- Agreement with human ranking
- Percentage of rejected low-quality items

---

# 13. Deduplication

Use multiple layers.

## Layer 1: exact URL

Canonicalize URLs by removing:

- Tracking parameters
- Fragments
- Duplicate trailing slashes
- Known redirect wrappers

## Layer 2: external source ID

Examples:

- arXiv paper ID
- GitHub repository full name
- GitHub release ID

## Layer 3: content hash

Normalize title and excerpt, then calculate SHA-256.

## Layer 4: title similarity

Use token similarity or rapidfuzz.

## Layer 5: semantic similarity

Use embeddings only for the final shortlist or uncertain cases to reduce cost.

## Layer 6: cross-source story grouping

Several websites may report the same model announcement. Store them as separate sources linked to one story cluster.

---

# 14. LLM Output Contract

Require JSON output rather than uncontrolled prose.

Example:

```json
{
  "headline": "LangGraph adds improved persistence controls",
  "category": "Agent Frameworks",
  "summary": "A concise, evidence-grounded summary.",
  "why_it_matters": "The practical importance for developers.",
  "limitations": ["Limitation one", "Limitation two"],
  "target_audience": ["AI engineers", "backend developers"],
  "claims": [
    {
      "text": "Claim made in the summary",
      "source_url": "https://official-source.example"
    }
  ],
  "confidence": 0.88
}
```

Validation rules:

- Headline length limit
- Summary word limit
- At least one source URL
- No source URL outside supplied evidence
- No unsupported numerical claim
- Confidence within `[0, 1]`
- Limitations required for research/model stories
- Reject malformed JSON

---

# 15. Automated Quality Review

The review node should score the complete issue.

## Checks

- Every story has a working source link
- No duplicated story
- Correct publication period
- Required sections present
- Minimum and maximum story count
- Summary length limits
- No unsupported claims
- No obvious contradictions
- Correct HTML structure
- PDF rendered successfully
- No empty section
- No leaked prompt or API data
- No offensive or inappropriate content
- Issue title and number are correct

## Example review output

```json
{
  "approved": false,
  "quality_score": 78,
  "issues": [
    {
      "type": "duplicate",
      "article_ids": ["a12", "a19"],
      "severity": "medium"
    },
    {
      "type": "unsupported_claim",
      "article_id": "a24",
      "severity": "high"
    }
  ],
  "action": "revise"
}
```

## Routing

```text
quality >= 85 and no high-severity issue -> generate final draft
quality < 85 and retries remaining -> revise
high-severity issue -> human review
retry limit reached -> human review
```

---

# 16. Human-in-the-Loop Design

Do not keep a GitHub runner waiting for human approval.

## Generation workflow

1. Generate draft.
2. Save database state.
3. Upload HTML/PDF preview.
4. Mark issue `reviewing`.
5. End GitHub Action.

## Review

Reviewer opens an admin page or GitHub-provided preview and chooses:

- Approve
- Request changes
- Reject

## Sending workflow

A separate workflow loads the approved issue and sends it.

### MVP approval options

From simplest to strongest:

1. Manual GitHub Actions input
2. Database status edited through a protected admin script
3. Streamlit admin dashboard
4. FastAPI + simple frontend
5. Slack/Telegram approval integration

For placement value, a minimal FastAPI admin endpoint plus a simple protected dashboard is stronger than manually editing the database.

---

# 17. Complete LangGraph Design

## Suggested nodes

```text
initialize_issue
collect_sources
normalize_items
validate_items
deduplicate_items
rank_items
select_items
summarize_items
review_summaries
revise_failed_summaries
assemble_issue
review_issue
render_html
render_pdf
upload_artifacts
request_human_approval
finalize_approved_issue
prepare_deliveries
send_batch
process_delivery_results
complete_issue
handle_failure
```

## Suggested state

```python
class NewsletterState(TypedDict):
    run_id: str
    issue_id: str
    issue_number: int
    period_start: str
    period_end: str

    collected_item_ids: list[str]
    selected_item_ids: list[str]
    completed_summary_ids: list[str]
    failed_summary_ids: list[str]

    quality_report: dict | None
    approval_decision: str | None

    html_object_key: str | None
    pdf_object_key: str | None

    current_stage: str
    retry_counts: dict[str, int]
    errors: list[dict]
```

Do not place full articles or PDF bytes inside graph state. Store records in PostgreSQL/R2 and keep only identifiers in state.

## Routing examples

```text
review_summaries:
  all valid -> assemble_issue
  retryable failures -> revise_failed_summaries
  retry limit reached -> request_human_approval

review_issue:
  approved -> render_html
  revisions required -> assemble_issue/revise
  severe failure -> request_human_approval

human decision:
  approved -> finalize_approved_issue
  changes requested -> revise
  rejected -> end
```

---

# 18. Failure and Retry Strategy

## Retryable failures

- HTTP timeout
- Temporary 5xx response
- Rate-limit response
- Temporary database connection failure
- Grok transient error
- R2 upload failure
- Resend temporary error
- PDF browser crash

Use:

- Exponential backoff
- Jitter
- Maximum attempts
- Per-operation timeout
- Circuit breaking for repeatedly failing sources

## Non-retryable failures

- Invalid API key
- Invalid schema
- Unauthorized domain
- Missing template
- Database migration mismatch
- Unsupported file format
- Invalid recipient
- Permanent email rejection

Send these directly to the failure handler.

## Retry granularity

Retry the smallest unit:

- One failed collector, not all collectors
- One failed article summary, not every summary
- One failed upload, not complete generation
- Failed email recipients only, not successful recipients

---

# 19. Idempotency

Idempotency ensures rerunning a workflow does not create duplicate effects.

## Issue key

```text
ai-weekly-2026-W29
```

Add a unique constraint to prevent two issues for the same period.

## Article identity

```text
source + external_id
or
canonical_url
or
content_hash
```

## Delivery identity

```text
newsletter_id + subscriber_id
```

Use a unique database constraint.

## Sending process

1. Insert pending delivery row.
2. If a row already exists as sent, skip.
3. Mark attempt as sending.
4. Call provider.
5. Store provider ID.
6. Mark sent.
7. On failure, store error and retry eligibility.

---

# 20. Security and Privacy

Subscriber emails are personal data. Handle them carefully.

## Required controls

- Store secrets only in GitHub Secrets or cloud secret storage.
- Never commit `.env`.
- Never print subscriber emails or API keys in logs.
- Encrypt traffic using TLS.
- Hash verification and unsubscribe tokens.
- Use least-privilege database credentials.
- Use separate development and production databases.
- Protect admin approval endpoints.
- Add rate limiting to subscription endpoints.
- Validate email addresses.
- Require user consent.
- Provide unsubscribe functionality.
- Avoid collecting unnecessary personal details.
- Create database backups.
- Rotate API keys if exposed.
- Enable branch protection.
- Run dependency/security scans.

## GitHub Actions permissions

Set minimal permissions:

```yaml
permissions:
  contents: read
```

Add other permissions only when required.

---

# 21. Repository Structure

```text
ai-intelligence-newsletter/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── generate-newsletter.yml
│       ├── send-newsletter.yml
│       └── cleanup.yml
│
├── src/
│   └── ai_newsletter/
│       ├── config.py
│       ├── main.py
│       ├── collectors/
│       │   ├── base.py
│       │   ├── arxiv.py
│       │   ├── github.py
│       │   ├── huggingface.py
│       │   └── rss.py
│       ├── processing/
│       │   ├── normalize.py
│       │   ├── validate.py
│       │   ├── deduplicate.py
│       │   └── classify.py
│       ├── ranking/
│       │   ├── features.py
│       │   ├── scorer.py
│       │   └── evaluation.py
│       ├── llm/
│       │   ├── client.py
│       │   ├── prompts.py
│       │   ├── schemas.py
│       │   └── reviewer.py
│       ├── workflow/
│       │   ├── graph.py
│       │   ├── state.py
│       │   ├── nodes.py
│       │   └── routing.py
│       ├── newsletter/
│       │   ├── assembler.py
│       │   ├── renderer.py
│       │   └── pdf.py
│       ├── storage/
│       │   ├── database.py
│       │   └── object_store.py
│       ├── email/
│       │   ├── sender.py
│       │   ├── templates.py
│       │   └── webhooks.py
│       ├── api/
│       │   ├── app.py
│       │   ├── subscribers.py
│       │   ├── approvals.py
│       │   └── issues.py
│       └── models/
│           ├── db.py
│           └── domain.py
│
├── templates/
│   ├── newsletter.html.j2
│   ├── verification.html.j2
│   └── welcome.html.j2
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
│   ├── architecture.md
│   ├── database.md
│   ├── workflow.md
│   ├── operations.md
│   └── threat-model.md
├── sample_output/
├── scripts/
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── README.md
└── plan.md
```

---

# 22. Step-by-Step Implementation Roadmap

# Stage 0 — Planning and constraints

## Goals

- Freeze MVP scope.
- Select 3–5 sources.
- Define newsletter sections.
- Define measurable success criteria.
- Create repository and issue tracker.

## Tasks

- Choose project name.
- Decide weekly schedule.
- Decide target subscriber count for MVP.
- Estimate Grok budget.
- Define sections:
  - Research spotlight
  - Trending repositories
  - Model/framework releases
  - Industry updates
  - Weekly trend insight
- Create initial architecture diagram.
- Create `.env.example`.
- Write initial README.

## Exit criteria

- Clear scope document
- Source list approved
- Stack fixed
- Repository created
- No unnecessary features

---

# Stage 1 — Local deterministic pipeline

## Goals

Generate a newsletter locally without LangGraph or cloud dependencies.

## Tasks

1. Build arXiv collector.
2. Build GitHub collector.
3. Build RSS collector.
4. Normalize all records.
5. Add date filtering.
6. Add exact duplicate removal.
7. Add basic scoring.
8. Select top items.
9. Render simple HTML from mock summaries.
10. Save JSON intermediate outputs.
11. Add unit tests.

## Focus

- Correct data
- Stable schemas
- Timeouts
- API rate limits
- Test fixtures
- Clear logs

## Exit criteria

Running:

```bash
python -m ai_newsletter.main generate --local
```

produces a valid HTML file from at least three data sources.

---

# Stage 2 — PostgreSQL persistence

## Goals

Persist subscribers, articles, issues, and workflow metadata.

## Tasks

1. Create Neon project.
2. Configure development and production URLs.
3. Add SQLAlchemy models.
4. Add Alembic.
5. Create initial migration.
6. Implement repositories/services.
7. Add unique constraints.
8. Store source items and avoid repeat insertion.
9. Create issue records.
10. Add integration tests using test database.

## Exit criteria

- Repeated ingestion does not duplicate records.
- Issue can be reconstructed from database.
- Database migrations work from empty state.
- Tests validate constraints.

---

# Stage 3 — LLM summarization

## Goals

Add Grok summaries only after deterministic filtering.

## Tasks

1. Create xAI client wrapper.
2. Define strict Pydantic output schema.
3. Create versioned prompts.
4. Limit content size.
5. Add cache by content hash + prompt version.
6. Track token usage.
7. Add retry/backoff.
8. Add summary validation.
9. Add source-claim mapping.
10. Test malformed output handling.

## Exit criteria

- Selected items receive valid structured summaries.
- Invalid responses are retried or rejected.
- Token usage is recorded.
- Unchanged items are not summarized repeatedly.

---

# Stage 4 — Ranking and deduplication improvements

## Goals

Make content selection defensible and measurable.

## Tasks

1. Add weighted ranking features.
2. Add GitHub star velocity.
3. Add source credibility weights.
4. Add fuzzy title matching.
5. Add semantic duplicate detection for uncertain pairs.
6. Create a manually labeled evaluation sample.
7. Compute Precision@K and NDCG@K.
8. Document the ranking formula.
9. Add feature explanations to logs.

## Exit criteria

- Ranking is reproducible.
- Duplicate rate is measured.
- Human evaluation shows useful top-K selection.
- Ranking does not rely only on LLM opinion.

---

# Stage 5 — HTML, PDF, and object storage

## Goals

Generate professional archived issues.

## Tasks

1. Design responsive Jinja2 HTML template.
2. Include source links.
3. Include issue metadata.
4. Add unsubscribe footer.
5. Add print CSS.
6. Generate PDF with Playwright.
7. Validate file size and page count.
8. Create R2 bucket.
9. Upload HTML and PDF.
10. Save object keys in PostgreSQL.
11. Create signed preview URLs.

## Exit criteria

- HTML works on desktop and mobile.
- PDF renders correctly.
- Files survive after the GitHub runner ends.
- Previous issues remain accessible.

---

# Stage 6 — LangGraph orchestration

## Goals

Add state, retries, conditional review, and checkpointing.

## Tasks

1. Define minimal graph state.
2. Implement nodes around existing services.
3. Add conditional routes.
4. Add retry counters.
5. Add Postgres checkpointer.
6. Persist thread/run IDs.
7. Add failure node.
8. Test resume after simulated failure.
9. Ensure state stores IDs, not large blobs.
10. Add workflow event logging.

## Exit criteria

- Workflow resumes from a checkpoint.
- Failed article summaries can retry independently.
- Current stage is visible in database.
- Retry loops terminate safely.

---

# Stage 7 — Human approval

## Goals

Ensure no public issue is sent without approval.

## Tasks

1. Create review status model.
2. Create protected FastAPI approval endpoints.
3. Build simple review page.
4. Display HTML/PDF preview.
5. Support approve, reject, request changes.
6. Record reviewer and comments.
7. Trigger separate send workflow after approval.
8. Add audit log.

## Exit criteria

- GitHub generation job ends while awaiting approval.
- Approval is persisted.
- Rejected issue cannot be sent.
- Approved issue can trigger sending.

---

# Stage 8 — Subscriber and email system

## Goals

Safely manage recipients and delivery.

## Tasks

1. Create subscription endpoint.
2. Send verification email.
3. Activate only verified users.
4. Create unsubscribe endpoint.
5. Verify sending domain.
6. Configure SPF, DKIM, and DMARC.
7. Implement individual/batch sending.
8. Precreate delivery records.
9. Apply unique delivery constraint.
10. Process Resend webhooks.
11. Retry failed recipients only.
12. Stop sending to bounced/unsubscribed users.

## Exit criteria

- Subscriber can verify and unsubscribe.
- No duplicate issue is sent to one subscriber.
- Failed recipient can be retried safely.
- Delivery status is visible.

---

# Stage 9 — GitHub Actions automation

## Goals

Run without the laptop.

## Workflows

### `ci.yml`

- Install dependencies
- Lint
- Type-check
- Run tests
- Validate migrations

### `generate-newsletter.yml`

- Scheduled weekly
- Manual trigger
- Collect and generate
- Upload preview
- End at approval state

### `send-newsletter.yml`

- Manual/API trigger
- Confirm approved issue
- Send pending deliveries
- Update issue status

### `cleanup.yml`

- Remove expired temporary data
- Archive old logs
- Check free-tier usage

## Cautions

- Add `concurrency`.
- Add timeout.
- Do not expose secrets.
- Use manual trigger fallback.
- Do not use Actions artifacts as permanent archive.
- Avoid overcomplicated YAML.

## Exit criteria

- Weekly issue generates while laptop is off.
- Manual rerun works.
- Overlapping runs are blocked.
- Logs explain failures clearly.

---

# Stage 10 — Testing and observability

## Unit tests

- URL canonicalization
- Date filtering
- Ranking
- Deduplication
- Prompt output validation
- Delivery idempotency
- Status transitions

## Integration tests

- Collector API fixtures
- PostgreSQL repositories
- R2 upload/download
- Resend mocked calls
- LangGraph checkpoint resume
- Full issue generation

## End-to-end test

```text
mock sources
-> collect
-> rank
-> summarize
-> review
-> render
-> approve
-> send to test recipient
```

## Metrics

- Items fetched per source
- Items rejected
- Duplicate percentage
- Top-K quality
- LLM success rate
- Token use and cost
- Generation duration
- Review score
- Revision count
- Email success/failure rate
- Subscriber growth
- Issue open/click rate, only where privacy and provider support are appropriate

---

# Stage 11 — Documentation and placement packaging

## Required documentation

- README
- Architecture diagram
- ER diagram
- LangGraph workflow diagram
- Data-source documentation
- Ranking explanation
- Failure-recovery explanation
- Security notes
- Cost analysis
- Limitations
- Demo video
- Sample issue
- API documentation

## Resume bullets

Use real metrics only.

Example template:

```text
- Built a cloud-automated AI intelligence pipeline integrating X APIs/RSS feeds
  and processing Y+ weekly items across research, open-source, and model updates.
- Designed a transparent ranking and multi-layer deduplication system that reduced
  repeated stories by Z% and improved human-rated Precision@10 to A.
- Implemented LangGraph-based conditional review, Postgres checkpoint recovery,
  human approval, and idempotent per-recipient email delivery.
- Automated HTML/PDF generation and weekly execution using GitHub Actions, Neon
  PostgreSQL, Cloudflare R2, Grok API, and Resend.
```

---

# 23. Full Production Workflow

## A. Scheduled generation

1. GitHub Actions starts.
2. It checks whether the weekly issue already exists.
3. It creates or resumes a workflow run.
4. Enabled source collectors execute with bounded concurrency.
5. Each source result is validated.
6. Failed sources retry according to policy.
7. Valid items are stored in PostgreSQL.
8. Date and topic filters remove irrelevant items.
9. Exact, fuzzy, and optional semantic duplicate detection runs.
10. Feature scores are calculated.
11. Top candidates are selected by section.
12. Grok creates structured summaries.
13. Each summary is schema-validated.
14. Claims are checked against supplied evidence.
15. Failed summaries retry individually.
16. The issue is assembled.
17. Automated issue quality review runs.
18. If rejected, the relevant content is revised.
19. HTML is rendered.
20. PDF is rendered.
21. Output files are validated.
22. Files are uploaded to R2.
23. Object keys are saved.
24. Issue status becomes `reviewing`.
25. Generation run completes.

## B. Human review

1. Reviewer signs in.
2. Reviewer opens draft preview.
3. Reviewer checks all source links.
4. Reviewer checks tone, length, and factuality.
5. Reviewer chooses approve, request changes, or reject.
6. Decision and comments are stored.
7. Changes return to a revision workflow.
8. Approval changes issue status to `approved`.

## C. Sending

1. Send workflow receives issue ID.
2. It confirms status is `approved`.
3. It locks the issue against duplicate concurrent sending.
4. It fetches active verified subscribers.
5. It inserts missing delivery rows.
6. It selects only pending/retryable deliveries.
7. It sends in rate-limited batches.
8. It records provider message IDs.
9. Successful rows become `sent`.
10. Failed rows record error details.
11. Retryable failures are retried.
12. Provider webhooks update delivered/bounced status.
13. Issue becomes `sent` only according to defined completion policy.
14. Final summary metrics are recorded.

## D. Recovery

1. A workflow fails.
2. `workflow_runs` records current node and error.
3. LangGraph checkpoint remains in PostgreSQL.
4. Temporary local files may disappear, but R2/DB data remains.
5. Manual or scheduled retry starts.
6. Existing issue/run is detected.
7. Completed nodes are not repeated unnecessarily.
8. Only failed work resumes.

---

# 24. Cost-Control Plan

## Fixed expected cost

- Domain registration/renewal
- Potentially no other fixed infrastructure cost during MVP

## Variable cost

- Grok API
- Email volume beyond free tier
- Database/storage beyond free tier

## Cost controls

- Maximum source items per run
- Maximum articles sent to LLM
- Maximum input characters/tokens
- Maximum output tokens
- Cache summaries
- Batch compatible operations where useful
- Maximum retries
- Monthly cost cap
- Store per-call usage
- Alert when thresholds are reached
- Use mock LLM mode in development
- Run public generation only weekly
- Avoid repeated PDF regeneration

---

# 25. Risks and Cautions

## 25.1 Hallucination

Risk: LLM introduces unsupported information.

Controls:

- Evidence-only prompts
- Structured claims with source links
- Automated claim checks
- Human approval
- Reject unsupported statistics
- Prefer official sources

## 25.2 Duplicate content

Risk: Same announcement appears from many sources.

Controls:

- Canonical URLs
- Hashes
- Title similarity
- Semantic clustering
- Cross-source story grouping

## 25.3 API rate limits

Risk: Collection fails or becomes expensive.

Controls:

- Caching
- ETags/conditional requests
- Request throttling
- Backoff
- Source-specific quotas
- Fetch only target period
- Store last successful cursor/timestamp

## 25.4 Email spam and account reputation

Controls:

- Verified domain
- SPF/DKIM/DMARC
- Double opt-in
- Unsubscribe link
- Low initial volume
- Clean subscriber list
- No purchased email lists
- Bounce processing
- Consistent sender name

## 25.5 Duplicate emails

Controls:

- Unique delivery constraint
- Issue lock
- Idempotency checks
- Retry only failed rows
- Provider IDs

## 25.6 Free-tier exhaustion

Controls:

- Monthly usage report
- Object lifecycle rules
- Database cleanup
- Small checkpoints
- No binary database storage
- Source and LLM limits

## 25.7 Temporary runner loss

Controls:

- Persist all important state in PostgreSQL/R2.
- Treat local files as disposable.
- Upload final artifacts before completing the run.

## 25.8 Source legal/terms issues

Controls:

- Prefer official APIs and RSS.
- Respect robots.txt and terms.
- Do not republish full copyrighted articles.
- Publish summaries and links.
- Store only required excerpts.
- Attribute every source.

## 25.9 Workflow complexity

Controls:

- Add LangGraph only after linear pipeline works.
- Keep nodes small.
- Avoid agent-for-every-step design.
- Define explicit state transitions.
- Limit loops.
- Document failure modes.

## 25.10 Security exposure

Controls:

- Secret scanning
- Protected branches
- Least privilege
- Dependency updates
- No sensitive logs
- Token rotation
- Admin authentication
- Signed URLs

---

# 26. Success Metrics

## Engineering metrics

- Scheduled-run success rate
- Mean generation time
- Resume success after failure
- Duplicate-send count: target zero
- Database constraint violation count
- Email success rate
- Source collector reliability
- Test coverage for critical modules

## Content metrics

- Precision@10
- Human approval rate
- Average revisions per issue
- Duplicate-story percentage
- Unsupported-claim rate
- Source-link validity rate
- Reader feedback

## Cost metrics

- Cost per issue
- LLM tokens per issue
- Storage growth per month
- Emails per month
- Database size

## Placement metrics

- Complete public README
- Architecture diagram
- Live demo
- Sample archived issues
- Test suite
- Meaningful commit history
- Real performance numbers
- Clear design trade-offs

---

# 27. Interview and Placement Question Bank

## A. Problem and product design

1. What problem does this project solve?
2. Why build this when many AI newsletters already exist?
3. Who is the target user?
4. What makes the platform different from a basic RSS summarizer?
5. Why did you choose a weekly newsletter instead of daily?
6. What is included in the MVP?
7. What did you intentionally exclude?
8. How do you define a successful issue?
9. How do you measure content quality?
10. How would you personalize newsletters later?

## B. Architecture

11. Explain the complete architecture end to end.
12. Why did you separate generation and sending?
13. Why is GitHub Actions the scheduler?
14. Why not deploy a permanently running server?
15. What happens when your laptop is off?
16. Where is state stored?
17. Which components are stateless?
18. Which components are stateful?
19. What is the single point of failure?
20. How would architecture change for 10,000 subscribers?
21. How would architecture change for daily execution?
22. Why use object storage separately from the database?
23. What is the role of FastAPI?
24. Why not implement everything in one Python script?
25. How do services communicate?

## C. PostgreSQL and data modelling

26. Why PostgreSQL instead of MongoDB?
27. Why Neon?
28. Why use one database instead of three?
29. Explain the subscriber schema.
30. Explain the newsletter issue schema.
31. Why is `newsletter_articles` a junction table?
32. Why is `email_deliveries` separate?
33. How do you prevent duplicate emails?
34. What foreign keys do you use?
35. Which columns need indexes?
36. Why use UUIDs?
37. When would integer IDs be better?
38. Where do you use JSONB?
39. Why not store everything in JSONB?
40. How do database transactions help sending?
41. How do you handle schema migrations?
42. What happens if a migration fails?
43. How do you back up the database?
44. How do you control database growth?
45. What isolation level do you need?
46. How do you handle concurrent send workflows?
47. How do you design an issue-level lock?
48. How do you query failed recipients only?
49. Why not store PDFs as database blobs?
50. How do you protect subscriber data?

## D. Data ingestion

51. Which sources do you collect?
52. Why did you prefer APIs and RSS?
53. How do you normalize different source formats?
54. How do you handle a source being unavailable?
55. How do you handle pagination?
56. How do you handle rate limits?
57. How do you handle API schema changes?
58. How do you detect outdated items?
59. How do you prevent collecting the same item weekly?
60. How do you validate publication dates?
61. How do you handle timezone differences?
62. How do you respect source terms and copyright?
63. How do you test collectors without hitting live APIs?
64. How do you add a new source?
65. What is the interface for a collector?

## E. Ranking

66. How do you rank news?
67. Why not rank only by recency?
68. Why not ask Grok to choose all stories?
69. What is GitHub star velocity?
70. How do you avoid favoring old repositories with many total stars?
71. What are source credibility weights?
72. How do you tune ranking weights?
73. How do you evaluate ranking quality?
74. Explain Precision@K.
75. Explain Recall@K.
76. Explain NDCG@K.
77. How do you create labeled evaluation data?
78. What happens when a new source has no historical metrics?
79. How do you handle popularity bias?
80. How do you balance research and industry news?

## F. Deduplication

81. How do you detect exact duplicates?
82. How do you canonicalize URLs?
83. Why use content hashes?
84. How do you detect differently worded reports of the same event?
85. Why is semantic deduplication expensive?
86. What similarity threshold did you choose and why?
87. What are false-positive duplicate matches?
88. How do you group multiple sources for one story?
89. How do you preserve the strongest source?
90. How do you measure deduplication performance?

## G. LLM/Grok integration

91. Why did you choose Grok?
92. Can the system switch to another model?
93. How do you make the model provider-independent?
94. What information is sent to Grok?
95. Why not send complete papers?
96. How do you control token cost?
97. How do you track token usage?
98. How do you cache summaries?
99. What is prompt versioning?
100. Why use structured output?
101. How do you validate model JSON?
102. How do you handle malformed responses?
103. How do you prevent hallucinations?
104. How do you verify numerical claims?
105. How do you ensure citations are real?
106. How do you handle model rate limits?
107. What temperature do you use and why?
108. When would you use a stronger model?
109. When would you use a cheaper model?
110. What happens if Grok is unavailable?
111. How would you evaluate summary quality?
112. What is faithfulness?
113. What is relevance?
114. What is coverage?
115. What is conciseness?
116. How do you test prompt changes?
117. How do you prevent prompt injection from source text?
118. Why should fetched content be treated as untrusted input?

## H. LangGraph and workflow orchestration

119. Why do you need LangGraph?
120. Which parts use normal Python instead?
121. What is graph state?
122. What is a checkpointer?
123. What is a thread ID?
124. What does checkpoint recovery provide?
125. How does human-in-the-loop work?
126. Why should a GitHub runner not wait for approval?
127. How do conditional edges work?
128. How do you avoid infinite revision loops?
129. What state should not be stored in LangGraph?
130. Why store identifiers rather than full content in state?
131. How do you resume after a PDF-generation failure?
132. How do you retry one article rather than the complete issue?
133. What is the difference between workflow state and business data?
134. What happens if checkpoint writing fails?
135. How do you inspect the failed node?
136. Could this be built without LangGraph?
137. When would using LangGraph be overengineering?

## I. GitHub Actions and cloud automation

138. How does a scheduled GitHub Action execute?
139. What is a runner?
140. Why is the runner filesystem temporary?
141. Where are secrets stored?
142. How do you configure manual triggers?
143. Why schedule at minute 17 instead of minute 0?
144. How do you prevent overlapping runs?
145. What is a concurrency group?
146. How do you set workflow timeouts?
147. How do you debug failed Actions?
148. Why not use Actions artifacts as permanent storage?
149. What happens if the scheduled run is delayed?
150. How do you rerun safely?
151. What permissions does the workflow need?
152. What are risks of third-party Actions?
153. How do you pin dependencies/actions?
154. How would you migrate to Cloud Run, Lambda, or a queue later?

## J. Email system

155. Why not use a personal Gmail account for production?
156. Why use a custom domain?
157. What are SPF, DKIM, and DMARC?
158. Why send individual emails?
159. Why not put all users in BCC?
160. How does double opt-in work?
161. How does unsubscribe work?
162. How do you store unsubscribe tokens securely?
163. What is a hard bounce?
164. What is a soft bounce?
165. How do webhooks update delivery status?
166. How do you prevent duplicate sending?
167. What happens if 80 of 100 emails succeed?
168. How do you retry the remaining 20?
169. Why include a hosted PDF link instead of a large attachment?
170. How do you handle provider rate limits?
171. How do you protect sender reputation?
172. How do you test email without sending to real subscribers?
173. What happens when a user unsubscribes during sending?

## K. Reliability

174. What failures are retryable?
175. What failures are non-retryable?
176. What is exponential backoff?
177. Why add jitter?
178. What is idempotency?
179. What is an idempotency key?
180. How do you avoid duplicate issue generation?
181. How do you avoid partial-state corruption?
182. How do transactions help?
183. What happens if R2 upload succeeds but DB update fails?
184. How would you reconcile inconsistent records?
185. How do you design a cleanup job?
186. How do you validate generated PDFs?
187. How do you define issue completion?
188. How do you test fault recovery?
189. How do you simulate external API failures?
190. What alerts should be generated?

## L. Security and privacy

191. What sensitive data does the system store?
192. How do you protect emails in logs?
193. How do you handle leaked API keys?
194. Why hash verification tokens?
195. What is least privilege?
196. How do you secure admin approval?
197. How do you prevent SQL injection?
198. How do Pydantic and SQLAlchemy help validation?
199. How do you prevent SSRF from arbitrary source URLs?
200. How do you prevent prompt injection?
201. How do you validate webhook signatures?
202. How do you rate-limit subscription endpoints?
203. How do you manage secrets locally?
204. Why should production and development databases be separate?
205. How do you delete a subscriber’s data?

## M. Testing

206. What are your unit tests?
207. What are your integration tests?
208. What is your end-to-end test?
209. How do you mock Grok?
210. How do you mock GitHub/arXiv APIs?
211. How do you test retry behaviour?
212. How do you test idempotency?
213. How do you test migrations?
214. How do you test email templates?
215. How do you test HTML on different email clients?
216. How do you test checkpoint resume?
217. Which modules need the highest test coverage?
218. How do you prevent flaky tests?

## N. Performance and scalability

219. What is the current bottleneck?
220. How do you parallelize collectors?
221. Why use bounded concurrency?
222. How many database connections are safe?
223. How do you batch inserts?
224. How do you batch LLM requests?
225. How do you scale to 10,000 subscribers?
226. When do you need a queue such as Celery/SQS?
227. When do you need Redis?
228. How do you partition email sending?
229. How do you avoid exhausting database connections?
230. How would you implement horizontal scaling?
231. What would move from GitHub Actions to a persistent service?
232. How do you reduce generation latency?
233. How do you estimate storage growth?

## O. Cost and trade-offs

234. Which parts are actually free?
235. Which parts can create variable costs?
236. How do you enforce a monthly Grok budget?
237. Why choose Neon over Supabase?
238. Why choose R2 over S3?
239. What are the limitations of free tiers?
240. What happens when Neon storage reaches its limit?
241. What happens when Resend volume grows?
242. What is the cost per issue?
243. Which optimizations save the most money?
244. When should you pay for better reliability?
245. Which component would you replace first at scale?

## P. Behavioral and project ownership

246. What was the hardest engineering problem?
247. What design decision did you change?
248. What trade-off are you least satisfied with?
249. What bug taught you the most?
250. How did you prioritize features?
251. What did you measure before optimizing?
252. What would you build differently now?
253. What part did you personally implement?
254. How did you validate that users found it useful?
255. What are the current limitations?
256. What is the next planned improvement?
257. How does this project demonstrate backend skills?
258. How does this project demonstrate ML/AI skills?
259. How does this project demonstrate system-design skills?
260. Why is this more than an LLM wrapper?

---

# 28. Strong Interview Answers to Prepare

## Why PostgreSQL?

> The core entities have strong relationships and consistency requirements. PostgreSQL gives me foreign keys, transactions, joins, and database-level unique constraints for idempotent delivery. JSONB still gives flexibility for LLM metadata and evolving workflow fields.

## Why LangGraph?

> I did not use LangGraph for deterministic collection or transformation. I used it for conditional quality-review routing, bounded revision loops, checkpoint-based recovery, and human approval. Those requirements make the workflow stateful rather than purely linear.

## Why GitHub Actions?

> The pipeline runs weekly, so a permanent server would be unnecessary for the MVP. GitHub Actions provides scheduled and manual cloud execution without depending on my laptop. Persistent state is stored externally because runners are temporary.

## How do you prevent duplicate emails?

> Each recipient-issue pair has a unique database constraint. Sending reads only pending or retryable delivery rows. Successful rows remain sent, so rerunning the workflow cannot send the same issue to the same subscriber again.

## How do you prevent hallucinations?

> I fetch information from APIs and official sources before calling the LLM. Grok receives only selected evidence, returns structured claims with source links, and an automated reviewer checks support. A human approves every public issue.

## Why not ask the LLM to rank everything?

> Metadata signals such as recency, source credibility, star velocity, release activity, and code availability are deterministic and explainable. The LLM is used only as a secondary semantic signal, which reduces cost and makes ranking measurable.

## What happens if the workflow stops?

> The current run, node, and checkpoints are stored in PostgreSQL. Generated files are stored in R2. A retry detects the existing issue and resumes failed work instead of repeating successful collection, summarization, or delivery.

---

# 29. Demo Plan

Prepare a 2–3 minute demo.

1. Show architecture diagram.
2. Open database tables briefly.
3. Trigger `generate-newsletter.yml`.
4. Show source collection logs.
5. Show ranking scores and duplicate removal.
6. Show one structured Grok summary.
7. Show automated quality report.
8. Open HTML/PDF preview.
9. Request a change or simulate rejection.
10. Show revision route.
11. Approve the issue.
12. Trigger sending.
13. Show received test email.
14. Show delivery record.
15. Show archived issue.
16. Simulate a failure and demonstrate resume.

---

# 30. Final One-Year Execution Strategy

## Months 1–2

- Local pipeline
- Three sources
- Database
- Basic HTML
- Send only to yourself

## Months 3–4

- Grok integration
- Ranking
- Deduplication
- PDF and R2
- GitHub Actions

## Months 5–6

- LangGraph
- Checkpoints
- Human approval
- Failure recovery

## Months 7–8

- Subscriber verification
- Custom domain
- Resend
- Delivery tracking

## Months 9–10

- Evaluation dataset
- Ranking metrics
- Better quality review
- Admin dashboard

## Months 11–12

- Improve documentation
- Add real metrics
- Record demo
- Prepare interview answers
- Decide whether to continue, open-source, or archive

---

# 31. Final Priorities

Focus most strongly on:

1. Reliable multi-source ingestion
2. Explainable ranking
3. Strong deduplication
4. Evidence-linked LLM summaries
5. Idempotent email delivery
6. Persistent checkpoint recovery
7. Human approval
8. Clean database design
9. Tests and observability
10. Documentation and measurable results

Do not spend excessive time on:

- Fancy frontend animations
- Too many agents
- Too many sources
- Complex microservices
- Premature large-scale architecture
- Generating visually heavy PDFs
- Adding features without evaluation

---

# 32. Recommended MVP Stack Summary

```text
Repository and automation:
GitHub + GitHub Actions

Application:
Python + FastAPI + Pydantic

Workflow:
LangGraph only for conditional stateful stages

Database:
Neon PostgreSQL

Object storage:
Cloudflare R2

LLM:
Grok/xAI API

Newsletter rendering:
Jinja2 + Playwright

Email:
Resend + verified custom domain

Testing:
pytest + mocked external APIs

Database migrations:
Alembic

Code quality:
Ruff + mypy
```

---

# 33. Official References

The limits and prices below can change. Recheck them before deployment.

- Neon pricing: https://neon.com/pricing
- Neon plans: https://neon.com/docs/introduction/plans
- Cloudflare R2 pricing: https://developers.cloudflare.com/r2/pricing/
- GitHub Actions billing: https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions
- GitHub Actions trigger documentation: https://docs.github.com/actions/using-workflows/events-that-trigger-workflows
- GitHub Actions workflow syntax: https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions
- Resend pricing: https://resend.com/pricing
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph checkpointers: https://docs.langchain.com/oss/python/integrations/checkpointers
- xAI quickstart: https://docs.x.ai/developers/quickstart
- xAI pricing: https://docs.x.ai/developers/pricing
- xAI rate limits: https://docs.x.ai/developers/rate-limits

---

# 34. Completion Checklist

## Core platform

- [ ] Repository created
- [ ] Architecture documented
- [ ] Local environment reproducible
- [ ] Collectors implemented
- [ ] Common schema implemented
- [ ] PostgreSQL migrations added
- [ ] Exact deduplication implemented
- [ ] Ranking implemented
- [ ] Grok structured summaries implemented
- [ ] Automated review implemented
- [ ] HTML generated
- [ ] PDF generated
- [ ] R2 upload implemented
- [ ] LangGraph checkpoints implemented
- [ ] Human approval implemented
- [ ] Subscriber verification implemented
- [ ] Unsubscribe implemented
- [ ] Delivery idempotency implemented
- [ ] Resend webhooks implemented
- [ ] GitHub scheduled workflow implemented
- [ ] Manual recovery workflow implemented

## Quality

- [ ] Every story has a source
- [ ] Unsupported claims rejected
- [ ] Duplicate rate measured
- [ ] Ranking evaluated
- [ ] Cost tracked
- [ ] Failure recovery tested
- [ ] Security review completed
- [ ] Database backup tested

## Placement

- [ ] README completed
- [ ] Architecture diagram included
- [ ] ER diagram included
- [ ] Workflow diagram included
- [ ] Sample issue included
- [ ] Demo video recorded
- [ ] Real metrics added
- [ ] Resume bullets finalized
- [ ] Interview questions practiced
- [ ] Limitations documented
