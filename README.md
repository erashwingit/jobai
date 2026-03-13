# Ashvani Job Bot 🤖

AI-powered job application automation system for Ashvani. Discovers, tailors, applies, and tracks job applications across LinkedIn, Naukri, and Indeed — with full interview prep automation.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Python Pipeline Orchestrator            │
│  Module 1: Discovery → Module 2: Resume →           │
│  Module 3: Apply → Module 4: Track → Module 5: Prep │
└──────────┬──────────────────────┬───────────────────┘
           │                      │
    ┌──────▼──────┐        ┌──────▼──────┐
    │ PDF Service │        │  Submitter  │
    │ Node + Pptr │        │  Node + Pw  │
    │  port 3001  │        │  port 3002  │
    └─────────────┘        └─────────────┘
```

### Microservices
| Service | Port | Tech | Purpose |
|---------|------|------|---------|
| `pdf-service` | 3001 | Node.js + Puppeteer | Jinja2 HTML → PDF |
| `submitter` | 3002 | Node.js + playwright-extra + stealth | Browser portal submission |
| `job-bot` | — | Python | Orchestrator |

---

## Security Model

**No passwords stored anywhere.**

Portal authentication uses session cookies only:

```bash
# One-time setup: open browser, log in manually, cookies auto-saved encrypted
node tools/export-cookies.js

# Cookies are AES-256-GCM encrypted to:
# ~/.config/ashvani-job-bot/cookies.enc
```

The `COOKIE_SECRET` in `.env` is a 32-byte key used for AES-256-GCM encryption/decryption of cookies.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker + Docker Compose (recommended)

### Setup

```bash
# 1. Clone & configure
cp .env.example .env
# Edit .env with your API keys

# 2. Install Python deps
pip install -r requirements.txt
playwright install chromium

# 3. Export portal cookies (one-time)
cd tools && npm install && node export-cookies.js

# 4. Start microservices
docker compose up -d pdf-service submitter

# 5. Run pipeline
python scripts/run_pipeline.py --dry-run     # Test first
python scripts/run_pipeline.py               # Full run
```

### Docker (Full Stack)

```bash
docker compose up
```

---

## Email Monitoring (n8n)

Email monitoring runs **automatically via n8n** every 30 minutes — not GitHub Actions.

### Setup n8n Email Workflow

1. **Install n8n**: `npx n8n` or via Docker
2. **Import workflow**: `n8n/email_monitor_workflow.json`
3. **Configure credentials** in n8n:
   - Gmail OAuth2 (minimal scope: `gmail.readonly`)
   - Google Sheets OAuth2
   - Telegram Bot API
4. **Set environment variables** in n8n:
   - `SHEETS_ID` — your Google Sheets spreadsheet ID
   - `TELEGRAM_CHAT_ID` — your Telegram chat ID

The workflow:
- Polls Gmail every 30 minutes for job-related emails
- Classifies emails: `INTERVIEW_SCHEDULED` / `OFFER_RECEIVED` / `REJECTED` / `APPLIED`
- Updates Google Sheets tracker automatically
- Sends Telegram notification for each update
- Triggers interview prep pipeline on interview detection

---

## Modules

| Module | Description |
|--------|-------------|
| **Discovery** | Scrapes LinkedIn, Naukri, Indeed. Deduplicates via SQLite. LLM-scores fit. |
| **Resume** | Tailors YAML resume per job → Jinja2 HTML → Puppeteer PDF. ATS-scores result. |
| **Application** | Cookie-authenticated bots for LinkedIn Easy Apply, Naukri, Indeed. |
| **Tracker** | Google Sheets as primary tracker. n8n email monitor updates status automatically. |
| **Interview Prep** | STAR story generator + company research + Glassdoor scraping → Google Docs. |

---

## Configuration

| File | Purpose |
|------|---------|
| `config/profile.yaml` | Candidate profile: skills, preferences, target roles |
| `config/master_resume.yaml` | Master resume template for tailoring |
| `config/settings.yaml` | Pipeline settings: score thresholds, rate limits |
| `.env` | Secrets (never commit) |

---

## CI/CD

Only security scanning runs in GitHub Actions:

```
.github/workflows/security_scan.yml  ← Bandit + detect-secrets (runs on push)
```

Email monitoring is handled entirely by **n8n** (see above).

---

## Tracker Schema (Google Sheets)

| Column | Description |
|--------|-------------|
| Job ID | Unique identifier |
| Company | Company name |
| Role | Job title |
| Portal | linkedin / naukri / indeed |
| Applied Date | ISO date |
| Status | APPLIED / INTERVIEW_SCHEDULED / OFFER_RECEIVED / REJECTED |
| Interview Date | Scheduled date (from email) |
| Interviewer | Contact name |
| Prep Sheet Link | Google Docs URL |
| Notes | Auto-populated from email snippets |

---

## License

Private — for personal use only.
