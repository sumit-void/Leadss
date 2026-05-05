# LeadMiner

Simple Google Maps lead scraper that collects business leads **without websites** — your ideal prospects for digital services.

## What It Does

1. **Scrapes Google Maps** using search queries you define
2. **Filters automatically** — keeps only leads that:
   - ❌ Do NOT have a website
   - ✅ DO have a phone number
   - ⭐ Have 2.0+ rating (or unrated)
3. **Saves to database** — each scrape run is a separate batch (never overwrites old data)
4. **Dashboard** — view, filter, and download leads as Excel files

## Files

| File | Purpose |
|------|---------|
| `batch_scraper.py` | The scraper — reads queries, scrapes Google Maps, saves to DB |
| `database.py` | SQLite database manager |
| `app.py` | Streamlit dashboard (view + download leads, edit queries) |
| `queries.txt` | Your search queries (one per line) |

## Setup

```bash
pip install -r requirements.txt
playwright install
```

## Usage

### 1. Add your queries
Edit `queries.txt` — one search per line:
```
interior designer in Dubai
beauty salon in Mumbai
dental clinic in London
```

### 2. Run the scraper
```bash
python batch_scraper.py
```

Options:
- `--max 50` — max results per query (default: 100)
- `--headed` — show browser window
- `--concurrency 3` — parallel tabs (default: 5)

### 3. View leads in dashboard
```bash
streamlit run app.py
```

The dashboard lets you:
- Switch between different scrape batches
- Search and filter leads
- Download filtered leads as Excel (split into tabs of 20)
- Edit your queries.txt directly

## AWS EC2 Deployment (Ubuntu)

### First Time Setup (run once)

```bash
# 1. Update system & install dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git tmux chromium-browser

# 2. Clone your repo
git clone https://github.com/sumit-void/Leadss.git
cd Leadss

# 3. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Install Python packages
pip install -r requirements.txt
```

> **Note:** You do NOT need `playwright install`. The scraper auto-detects the system `chromium-browser` you installed in step 1.

---

### Run Scraper (in tmux)

```bash
# Start a tmux session for scraper
tmux new -s scraper

# Activate venv and run
cd ~/Leadss
source venv/bin/activate
python batch_scraper.py

# Detach from tmux: press Ctrl+B, then D
```

### Run Dashboard (in tmux)

```bash
# Start a tmux session for dashboard
tmux new -s dashboard

# Activate venv and run
cd ~/Leadss
source venv/bin/activate
streamlit run app.py --server.port 8501 --server.address 0.0.0.0

# Detach from tmux: press Ctrl+B, then D
```

Dashboard will be live at: `http://<your-ec2-ip>:8501`

> Make sure port **8501** is open in your EC2 Security Group (Inbound Rules → Custom TCP → 8501 → 0.0.0.0/0)

---

### Quick Reference — tmux Commands

| Command | What It Does |
|---------|-------------|
| `tmux new -s scraper` | Start new session named "scraper" |
| `tmux new -s dashboard` | Start new session named "dashboard" |
| `tmux ls` | List all running sessions |
| `tmux attach -t scraper` | Reattach to scraper session |
| `tmux attach -t dashboard` | Reattach to dashboard session |
| `tmux kill-session -t scraper` | Kill scraper session |
| `Ctrl+B, then D` | Detach (leave running in background) |

### All-in-One (copy-paste after first setup)

If your server rebooted or you need to restart everything:

```bash
# Kill old sessions if any
tmux kill-server 2>/dev/null

# Start scraper in background
tmux new -d -s scraper "cd ~/Leadss && source venv/bin/activate && python batch_scraper.py"

# Start dashboard in background
tmux new -d -s dashboard "cd ~/Leadss && source venv/bin/activate && streamlit run app.py --server.port 8501 --server.address 0.0.0.0"

# Verify both are running
tmux ls
```

---

## Excel Download Format

When you download, leads are split across Excel tabs:
- Sheet "Leads 1-20" → first 20
- Sheet "Leads 21-40" → next 20
- etc.
