# LeadGen — Email Scraper for Cold Outreach

Finds businesses on Google → crawls their websites → extracts emails → scores them for outreach.

**100% Free. No Docker. No cloud. Just Python.**

---

## Setup (2 minutes)

```bash
pip install -r requirements.txt
playwright install chromium
```

That's it. Done.

---

## Usage

### 1. Add your search queries

Edit `queriess.txt` — one search per line:

```
real estate agency in Dubai
dental clinic in Dubai
beauty salon in Abu Dhabi
```

### 2. Run the scraper

```bash
python run.py
```

This does **everything automatically**:
- Searches Google for each query
- Finds business websites
- Crawls each website (homepage + contact/about pages)
- Extracts emails (4 methods: mailto, schema, HTML, regex)
- Scores each website (higher score = needs more help = better lead)
- Generates personalized outreach openers
- Saves everything to SQLite database

### 3. View leads

```bash
streamlit run app.py
```

Opens a dashboard where you can:
- View all leads with emails and scores
- Filter by batch, score, email, search
- Download Excel or CSV
- Edit your queries

---

## Options

```bash
python run.py --pages 3        # Search 3 Google pages per query (default: 2)
python run.py --max 50         # Max 50 businesses per query (default: 30)
python run.py --headed         # Show browser (useful for debugging)
python run.py --file my.txt    # Use different queries file
```

---

## What Gets Extracted

For each business:

| Data | Source |
|------|--------|
| Business name | Google Search |
| Website URL | Google Search |
| Emails | Website crawl (mailto, schema, HTML, regex) |
| Phone numbers | Website crawl |
| Social links | Website crawl (Facebook, Instagram, LinkedIn, etc.) |
| CMS detected | Website crawl (WordPress, Shopify, Wix, etc.) |
| SSL status | Website crawl |
| Mobile-friendly | Website crawl |
| Page speed | Website crawl |
| Lead score | Auto-calculated (0-100) |
| Audit summary | Auto-generated |
| Outreach opener | Auto-generated personalized pitch |

---

## Files

| File | What it does |
|------|-------------|
| `run.py` | **Main script** — runs the full pipeline |
| `app.py` | Streamlit dashboard |
| `scraper.py` | Google Search scraper (Playwright) |
| `crawler.py` | Website crawler (async httpx) |
| `email_extractor.py` | Email extraction (4 methods) |
| `auditor.py` | Website quality scoring |
| `database.py` | SQLite database (auto-created) |
| `queriess.txt` | Your search queries |

---

## How Scoring Works

Higher score = business needs more help = better lead for you.

| Check | Points |
|-------|--------|
| Has email (can be contacted) | +15 |
| No SSL/HTTPS | +10 |
| Not mobile-friendly | +15 |
| Slow page load (>5s) | +15 |
| WordPress (common client) | +8 |
| Missing meta description | +5 |
| Missing H1 heading | +5 |
| No social media links | +5 |
| No contact form | +5 |

Score 70+ = Hot lead, reach out first.

---

## AWS EC2 (Free Tier)

```bash
# On Ubuntu EC2 (t2.micro — free for 12 months)
sudo apt update && sudo apt install -y python3-pip python3-venv chromium-browser git

git clone https://github.com/sumit-void/Leadss.git
cd Leadss
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run in tmux so it stays alive
tmux new -s scraper
python run.py
# Ctrl+B, D to detach

# Dashboard
tmux new -s dash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
# Open port 8501 in Security Group
```

---

## Tips

- Start with 2-3 queries to test, then add more
- Use `--headed` to see what the browser is doing
- If Google shows CAPTCHAs, wait 30 minutes and try again
- Queries with location (e.g., "dental clinic in Dubai") work best
- Export leads → import into your cold email tool (Instantly, Smartlead, etc.)
