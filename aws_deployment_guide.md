# AWS EC2 Deployment Guide — LeadGen Pro

Deploy the full lead generation system on AWS EC2 free tier.

---

## Recommended Instance

| Setting | Value |
|---------|-------|
| **AMI** | Ubuntu 22.04 LTS |
| **Instance Type** | t2.micro (free tier) or t3.small (better) |
| **Storage** | 20 GB gp3 (free tier: 30 GB) |
| **Region** | us-east-1 (cheapest) |

> **Free Tier Note**: t2.micro (1 vCPU, 1GB RAM) works but is tight with Docker. For production, t3.small (2 vCPU, 2GB RAM) at ~$15/mo is much better.

---

## Step 1: Launch EC2 Instance

1. Go to [AWS EC2 Console](https://console.aws.amazon.com/ec2/)
2. Click **Launch Instance**
3. Select **Ubuntu 22.04 LTS** AMI
4. Choose **t2.micro** (free tier eligible)
5. Create or select a **Key Pair** (download `.pem` file)
6. **Network Settings** → allow SSH (port 22)
7. **Storage**: 20+ GB
8. Launch

---

## Step 2: Configure Security Groups

Add these inbound rules:

| Type | Port | Source | Purpose |
|------|------|--------|---------|
| SSH | 22 | Your IP | Remote access |
| Custom TCP | 8000 | 0.0.0.0/0 | FastAPI |
| Custom TCP | 5432 | Your IP | PostgreSQL (optional) |

---

## Step 3: Connect & Install Docker

```bash
# Connect to your instance
ssh -i your-key.pem ubuntu@<ec2-public-ip>

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
sudo apt install -y docker.io docker-compose git

# Add user to docker group (avoids sudo)
sudo usermod -aG docker $USER

# IMPORTANT: Log out and back in
exit
ssh -i your-key.pem ubuntu@<ec2-public-ip>

# Verify Docker
docker --version
docker-compose --version
```

---

## Step 4: Deploy Application

```bash
# Clone repository
git clone https://github.com/sumit-void/Leadss.git
cd Leadss

# Create environment file
cp .env.example .env

# Edit .env if needed
nano .env

# Build and start all services
docker-compose up -d --build
```

First build takes 5-10 minutes (downloads images + installs Playwright).

---

## Step 5: Verify Deployment

```bash
# Check all containers are running
docker-compose ps

# Check API
curl http://localhost:8000/health

# Check logs
docker-compose logs -f api
```

API should be accessible at: `http://<ec2-public-ip>:8000/docs`

---

## Step 6: Start Scraping

```bash
# Enqueue all queries from queriess.txt
docker-compose exec api python -m scripts.seed_queries

# Or run a single search
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "roofing company texas", "max_pages": 2}'

# Monitor workers
docker-compose logs -f worker-search worker-crawl
```

---

## Swap File (Required for t2.micro)

t2.micro only has 1GB RAM. Add swap to prevent OOM:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## Auto-Start on Reboot

```bash
# Enable Docker to start on boot
sudo systemctl enable docker

# Create a restart script
cat << 'EOF' > ~/start_leadgen.sh
#!/bin/bash
cd ~/Leadss
docker-compose up -d
EOF

chmod +x ~/start_leadgen.sh

# Add to crontab
(crontab -l 2>/dev/null; echo "@reboot /home/ubuntu/start_leadgen.sh") | crontab -
```

---

## Useful Commands

```bash
# View all logs
docker-compose logs -f

# Restart everything
docker-compose restart

# Rebuild after git pull
git pull
docker-compose up -d --build

# Check disk usage
df -h
docker system df

# Clean up Docker (free space)
docker system prune -f

# Access PostgreSQL directly
docker-compose exec db psql -U leadgen -d leadgen

# Check Redis
docker-compose exec redis redis-cli ping
```

---

## Scaling on EC2

### Vertical (bigger instance)
Upgrade to t3.small/t3.medium for more RAM and CPU.

### Horizontal (more workers)
```bash
# Scale crawl workers
docker-compose up -d --scale worker-crawl=3

# Scale audit workers
docker-compose up -d --scale worker-audit=2
```

### Memory Optimization for Free Tier

In `docker-compose.yml`, add memory limits:
```yaml
services:
  db:
    mem_limit: 256m
  redis:
    mem_limit: 64m
  api:
    mem_limit: 256m
  worker-search:
    mem_limit: 256m
  worker-crawl:
    mem_limit: 256m
  worker-audit:
    mem_limit: 128m
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Container keeps restarting | `docker-compose logs <service>` to see error |
| Out of memory | Add swap (see above) or upgrade instance |
| Port 8000 not accessible | Check Security Group inbound rules |
| Playwright fails | Ensure Dockerfile installs browser deps |
| DB connection refused | Wait for health check: `docker-compose ps` |
| Search gets CAPTCHAs | Increase `REQUEST_DELAY_MIN/MAX` in `.env` |

---

## Cost Summary (Monthly)

| Resource | Free Tier | After Free Tier |
|----------|-----------|-----------------|
| EC2 t2.micro | $0 (12 months) | ~$8.50/mo |
| EBS 20GB | $0 (30GB free) | ~$1.60/mo |
| Data Transfer | $0 (100GB free) | varies |
| **Total** | **$0** | **~$10/mo** |
