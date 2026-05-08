# LeadGen Pro — Local Setup Instructions

Step-by-step guide to run the system locally with Docker.

---

## Prerequisites

1. **Docker Desktop** — [Download](https://docs.docker.com/get-docker/)
   - Windows: Docker Desktop for Windows
   - Mac: Docker Desktop for Mac
   - Linux: `sudo apt install docker.io docker-compose`

2. **Git** — [Download](https://git-scm.com/)

---

## Setup Steps

### 1. Clone the Repository

```bash
git clone https://github.com/sumit-void/Leadss.git
cd Leadss
```

### 2. Create Environment File

```bash
cp .env.example .env
```

The defaults work out of the box. Edit `.env` only if you want to:
- Change database credentials
- Enable Ollama AI auditing
- Adjust scraping delays

### 3. Build and Start

```bash
docker-compose up -d --build
```

**First run** takes 5-10 minutes (downloads PostgreSQL, Redis, installs Playwright Chromium).

### 4. Verify Everything is Running

```bash
docker-compose ps
```

You should see 6 services: `db`, `redis`, `api`, `worker-search`, `worker-crawl`, `worker-audit`

### 5. Open API Docs

Open in browser: **http://localhost:8000/docs**

---

## Usage

### Run a Search

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "dental clinic dubai", "max_pages": 2}'
```

### Bulk Search (from queries file)

```bash
docker-compose exec api python -m scripts.seed_queries
```

### View Leads

```bash
# All leads
curl http://localhost:8000/api/leads

# With filters
curl "http://localhost:8000/api/leads?niche=dental&min_score=50&has_email=true"

# Dashboard stats
curl http://localhost:8000/api/leads/stats
```

### Export Data

```bash
# CSV
curl http://localhost:8000/api/exports/csv -o leads.csv

# Excel
curl http://localhost:8000/api/exports/excel -o leads.xlsx
```

### Monitor Workers

```bash
docker-compose logs -f worker-search worker-crawl worker-audit
```

---

## Stopping

```bash
# Stop all services (keeps data)
docker-compose down

# Stop and DELETE all data
docker-compose down -v
```

---

## Running Without Docker (Development)

If you prefer running directly:

```bash
# 1. Install PostgreSQL and Redis locally
# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 3. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 4. Set environment variables
# Update .env with POSTGRES_HOST=localhost, REDIS_URL=redis://localhost:6379/0

# 5. Initialize database
python -m scripts.init_db

# 6. Start FastAPI
uvicorn app.main:app --reload --port 8000

# 7. Start Celery workers (separate terminals)
celery -A app.workers.celery_app worker -Q search -l info -c 2
celery -A app.workers.celery_app worker -Q crawl,email -l info -c 3
celery -A app.workers.celery_app worker -Q audit -l info -c 2
```
