# LeadGen Pro

**Scalable Lead Generation & Website Audit System**

Discovers businesses via Google Search → crawls their websites → extracts emails → audits website quality → generates outreach-ready leads.

Built with Python, FastAPI, PostgreSQL, Redis, Celery, Playwright, and Docker.

> **100% Free** — No paid APIs. Uses rule-based scoring + optional free local AI (Ollama).

---

## Architecture

```
Google Search ──→ Search Workers ──→ PostgreSQL
                        │
                        ▼
                  Crawl Workers ──→ Website Data
                        │
                   ┌────┴────┐
                   ▼         ▼
             Email Worker  Audit Worker
                   │         │
                   ▼         ▼
              Emails DB   Scores + Outreach
                        │
                        ▼
                   FastAPI Dashboard
                   (REST API + Export)
```

### Pipeline Flow
1. **Search**: Playwright scrapes Google Search for local businesses
2. **Crawl**: async httpx crawls homepage + contact/about/services pages
3. **Extract**: Multi-method email extraction (mailto, schema, regex, HTML)
4. **Audit**: Rule-based website quality scoring (+ optional Ollama AI)
5. **API**: FastAPI serves leads with filtering, export, and campaign tracking

---

## Tech Stack

| Component | Technology | Cost |
|-----------|-----------|------|
| API | FastAPI + Uvicorn | Free |
| Database | PostgreSQL 16 | Free |
| Queue | Redis 7 + Celery | Free |
| Scraping | Playwright (Chromium) | Free |
| Crawling | httpx + BeautifulSoup | Free |
| AI Audit | Rule-based / Ollama | Free |
| Container | Docker + Docker Compose | Free |
| Hosting | AWS EC2 Free Tier | Free |

---

## Quick Start

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- Git

### 1. Clone & Configure

```bash
git clone https://github.com/sumit-void/Leadss.git
cd Leadss

# Create environment file
cp .env.example .env
# Edit .env if needed (defaults work out of the box)
```

### 2. Start Everything

```bash
docker-compose up -d --build
```

This starts:
- **PostgreSQL** on port 5432
- **Redis** on port 6379
- **FastAPI** on port 8000
- **3 Celery workers** (search, crawl, audit)

### 3. Verify

```bash
# Check all services are running
docker-compose ps

# Open API docs
# http://localhost:8000/docs
```

### 4. Run Your First Search

```bash
# Via API
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "roofing company texas", "max_pages": 2}'

# Or bulk-enqueue from queries file
docker-compose exec api python -m scripts.seed_queries
```

### 5. View Results

```bash
# List leads
curl http://localhost:8000/api/leads

# Get stats
curl http://localhost:8000/api/leads/stats

# Export CSV
curl http://localhost:8000/api/exports/csv -o leads.csv

# Export Excel
curl http://localhost:8000/api/exports/excel -o leads.xlsx
```

---

## API Endpoints

### Leads
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/leads` | List leads (with filters, pagination) |
| GET | `/api/leads/stats` | Dashboard statistics |
| GET | `/api/leads/{id}` | Full lead detail (emails + audit) |
| PATCH | `/api/leads/{id}` | Update lead status |

**Filters**: `?status=audited&niche=roofing&min_score=50&has_email=true&search=texas`

### Audits
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/audits` | List all audits |
| GET | `/api/audits/{id}` | Audit detail |
| POST | `/api/audits/run` | Trigger audit for a business |

### Campaigns
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/campaigns` | List campaigns |
| POST | `/api/campaigns` | Create campaign |
| PATCH | `/api/campaigns/{id}` | Update status |

### Exports & Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/exports/csv` | Download CSV |
| GET | `/api/exports/excel` | Download Excel |
| POST | `/api/search` | Trigger new search |

### Interactive Docs
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Database Schema

```
businesses ──┬── websites (1:many)
             ├── emails (1:many)
             ├── audits (1:many)
             └── outreach_campaigns (1:many)
```

### Tables
- **businesses**: Discovered leads with status tracking and lead scores
- **websites**: Crawled page data (title, meta, headings, CMS, SSL, mobile)
- **emails**: Extracted emails with confidence scores and methods
- **audits**: Website quality audit results with category scores
- **outreach_campaigns**: Email outreach tracking

---

## Folder Structure

```
├── docker-compose.yml          # All services
├── Dockerfile                  # Container build
├── .env.example                # Environment template
├── requirements.txt            # Python dependencies
├── queriess.txt                # Search queries
│
├── app/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Settings (env vars)
│   │
│   ├── models/                 # SQLAlchemy models
│   │   ├── database.py         # Engine + sessions
│   │   ├── business.py         # Business/lead model
│   │   ├── website.py          # Crawled page model
│   │   ├── email_model.py      # Email model
│   │   ├── audit.py            # Audit model
│   │   └── campaign.py         # Campaign model
│   │
│   ├── api/                    # FastAPI endpoints
│   │   ├── router.py           # Main router
│   │   ├── leads.py            # Lead CRUD
│   │   ├── audits.py           # Audit endpoints
│   │   ├── campaigns.py        # Campaign endpoints
│   │   └── exports.py          # CSV/Excel + search trigger
│   │
│   ├── workers/                # Celery tasks
│   │   ├── celery_app.py       # Celery config
│   │   ├── search_worker.py    # Google Search scraping
│   │   ├── crawl_worker.py     # Website crawling
│   │   ├── email_worker.py     # Email extraction
│   │   └── audit_worker.py     # Website audit
│   │
│   ├── scrapers/               # Scraping logic
│   │   ├── google_search.py    # Playwright Google scraper
│   │   ├── website_crawler.py  # Async website crawler
│   │   └── email_extractor.py  # Multi-method email extraction
│   │
│   └── services/               # Business logic
│       ├── ai_audit.py         # AI audit (Ollama + rules)
│       └── lead_scorer.py      # Rule-based scoring
│
└── scripts/
    ├── init_db.py              # Create tables
    └── seed_queries.py         # Bulk-enqueue queries
```

---

## Configuration

All settings via environment variables (`.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `db` | Database host |
| `POSTGRES_PORT` | `5432` | Database port |
| `POSTGRES_USER` | `leadgen` | Database user |
| `POSTGRES_PASSWORD` | `leadgen_secret_2024` | Database password |
| `POSTGRES_DB` | `leadgen` | Database name |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `OLLAMA_BASE_URL` | *(empty)* | Ollama URL (optional, for AI audit) |
| `OLLAMA_MODEL` | `llama3` | Ollama model name |
| `MAX_SEARCH_PAGES` | `3` | Pages per Google search |
| `CRAWL_CONCURRENCY` | `5` | Max concurrent crawls |
| `REQUEST_DELAY_MIN` | `3` | Min delay between requests (sec) |
| `REQUEST_DELAY_MAX` | `7` | Max delay between requests (sec) |

---

## Optional: Free AI Audit with Ollama

To enable AI-powered audits (completely free, runs locally):

```bash
# Install Ollama (https://ollama.ai)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull llama3

# Add to .env
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3
```

Without Ollama, the system uses rule-based scoring (also works great).

---

## Monitoring

```bash
# View all container logs
docker-compose logs -f

# View specific worker
docker-compose logs -f worker-search
docker-compose logs -f worker-crawl
docker-compose logs -f worker-audit

# Check container status
docker-compose ps

# Restart a service
docker-compose restart worker-search
```

---

## Common Commands

```bash
# Start all services
docker-compose up -d --build

# Stop all services
docker-compose down

# Stop and remove all data
docker-compose down -v

# Rebuild after code changes
docker-compose up -d --build

# Run a one-off search
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "dental clinic dubai"}'

# Export leads with email only
curl "http://localhost:8000/api/exports/csv?has_email=true" -o leads_with_email.csv

# Export high-score leads
curl "http://localhost:8000/api/exports/csv?min_score=60" -o hot_leads.csv
```

---

## AWS EC2 Deployment

See [aws_deployment_guide.md](aws_deployment_guide.md) for full instructions.

**Quick version:**

```bash
# On Ubuntu 22.04 EC2 (t2.micro free tier)
sudo apt update && sudo apt install -y docker.io docker-compose git
sudo usermod -aG docker $USER
# Log out and back in

git clone https://github.com/sumit-void/Leadss.git
cd Leadss
cp .env.example .env
docker-compose up -d --build
```

Open Security Group port **8000** → API is live at `http://<ec2-ip>:8000/docs`

---

## License

Private — Internal use only.
