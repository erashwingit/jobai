# Ashvani Job Bot — Setup Guide

Complete step-by-step setup from a fresh clone to a running pipeline.

---

## Prerequisites

| Requirement | Minimum Version | Install |
|-------------|----------------|---------|
| Python | 3.10+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| Docker | 24+ | [docker.com](https://docker.com/get-started) *(optional but recommended)* |
| Git | any | pre-installed on most systems |
| openssl | any | pre-installed on macOS/Linux |

---

## Step 1 — Clone and Run Setup Script

```bash
git clone https://github.com/erashwingit/jobai.git
cd jobai
chmod +x scripts/setup.sh
./scripts/setup.sh
```

The setup script does everything automatically:
- Generates secure secrets (`COOKIE_SECRET`, `INTERNAL_TOKEN`)
- Creates `~/.config/ashvani-job-bot/` with locked-down permissions
- Copies `.env.example → .env` with secrets pre-filled
- Prompts you for API keys interactively
- Creates Python venv at `.venv/` and installs all deps
- Installs Node.js deps for `services/pdf-service`, `services/submitter`, `tools/`
- Runs `pytest tests/` as a smoke test

> **Idempotent:** Re-running `setup.sh` on an existing install skips steps already done (won't overwrite your `.env`).

---

## Step 2 — Get Free API Keys

### 🤖 Gemini API (Primary LLM)
1. Go to **[aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)**
2. Click **"Create API Key"** → copy the key
3. Add to `.env`: `GEMINI_API_KEY=your_key`

### ⚡ Groq API (Fallback LLM — Free Tier)
1. Go to **[console.groq.com/keys](https://console.groq.com/keys)**
2. Sign up (free) → click **"Create API Key"** → copy the key
3. Add to `.env`: `GROQ_API_KEY=your_key`
4. Free tier gives generous limits for `llama-3.3-70b-versatile`

### 📱 Telegram Bot (Notifications)
1. Open Telegram → message **[@BotFather](https://t.me/botfather)**
2. Send `/newbot` → follow prompts → copy the **HTTP API token**
3. Add to `.env`: `TELEGRAM_BOT_TOKEN=your_token`
4. Get your chat ID: message **[@userinfobot](https://t.me/userinfobot)** → copy the ID
5. Add to `.env`: `TELEGRAM_CHAT_ID=your_id`

### 📊 Google Sheets (Application Tracker)
1. Go to **[sheets.google.com](https://sheets.google.com)** → create a new spreadsheet named `Job Applications`
2. Copy the spreadsheet ID from the URL: `https://docs.google.com/spreadsheets/d/**COPY_THIS_ID**/edit`
3. Add to `.env`: `SHEETS_ID=your_spreadsheet_id`

---

## Step 3 — Google OAuth Setup (Sheets + Gmail + Calendar)

The bot uses Google APIs with minimal OAuth2 scopes. You need a `credentials.json` file.

### 3a. Create a Google Cloud Project
1. Go to **[console.cloud.google.com](https://console.cloud.google.com)**
2. Create a new project: **"ashvani-job-bot"**

### 3b. Enable APIs
In your project, navigate to **APIs & Services → Library** and enable:
- **Google Sheets API**
- **Gmail API** *(read-only scope for email monitoring)*
- **Google Calendar API** *(for interview scheduling)*
- **Google Drive API** *(for interview prep Docs)*

### 3c. Create OAuth Credentials
1. Go to **APIs & Services → Credentials**
2. Click **"Create Credentials" → "OAuth client ID"**
3. Application type: **Desktop App**
4. Name: `ashvani-job-bot`
5. Click **"Download JSON"**
6. Save the downloaded file to:
   ```
   ~/.config/ashvani-job-bot/credentials.json
   ```

### 3d. First-time OAuth Authorization
```bash
source .venv/bin/activate
python scripts/run_pipeline.py --module email
```
This opens your browser to grant the bot read access to Gmail. Token is saved automatically.

---

## Step 4 — Export Portal Cookies

The bot uses **encrypted session cookies** instead of storing passwords. This is a **one-time manual step** per portal.

```bash
node tools/export-cookies.js
```

**What happens:**
1. A visible Chromium browser window opens
2. You'll see LinkedIn and Naukri tabs open automatically
3. **Log in manually** to each portal in the browser (just like normal)
4. The script captures your session cookies
5. Cookies are encrypted with AES-256-GCM (using your `COOKIE_SECRET`) and saved to `~/.config/ashvani-job-bot/cookies.enc`
6. The browser closes automatically

> **Note:** Cookies typically last 30–90 days. Re-run this script when you see `CookieExpiredError`.

> **Security:** Your passwords are never stored anywhere. Only session tokens are captured.

---

## Step 5 — Edit Your Profile

Copy the example profile to get started:

```bash
cp config/profile.yaml.example config/profile.yaml
```

Edit `config/profile.yaml` with your real details:

```yaml
candidate:
  name: "Your Name"
  email: "your@email.com"
  target_roles:
    - "AI Engineer"
    - "ML Engineer"
  skills_primary:
    - Python
    - LLMs
    - PyTorch
  min_salary_lpa: 18
  work_mode: [remote, hybrid]
```

Also update `config/master_resume.yaml` with your actual work experience, education, and projects. This is the base from which all tailored resumes are generated.

---

## Step 6 — Start Microservices

The bot uses two Node.js microservices for PDF generation and browser automation:

```bash
# Start both services (recommended)
docker compose up -d

# Verify they're running
curl http://localhost:3001/health   # → {"status":"ok","service":"pdf-service"}
curl http://localhost:3002/health   # → {"status":"ok","service":"submitter"}
```

**Without Docker (manual):**
```bash
# Terminal 1 — PDF service
cd services/pdf-service && node index.js &

# Terminal 2 — Submitter service
cd services/submitter && node index.js &
```

---

## Step 7 — Test the Pipeline

```bash
source .venv/bin/activate

# Dry-run: discovers jobs + tailors resumes, does NOT submit any applications
python scripts/run_pipeline.py --dry-run

# Run a single module
python scripts/run_pipeline.py --module discovery  # just scrape jobs
python scripts/run_pipeline.py --module resume     # just tailor resumes

# Full pipeline (live applications)
python scripts/run_pipeline.py
```

---

## Step 8 — Set Up n8n Email Monitor

The email monitoring and tracker auto-update runs via **n8n** (not GitHub Actions).

### 8a. Deploy n8n

**Easiest: DigitalOcean 1-click** — [Deploy n8n on DigitalOcean](https://m.do.co/c/ashvani)
```bash
# Or run locally with Docker
docker run -it --rm \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n
```

### 8b. Import the Workflow
1. Open n8n at `http://your-server:5678`
2. Go to **Workflows → Import from file**
3. Select `n8n/email_monitor_workflow.json`

### 8c. Configure Credentials in n8n
In **Settings → Credentials**, create:
| Credential | Type | Details |
|-----------|------|---------|
| Gmail OAuth2 | Google (OAuth2) | Scope: `gmail.readonly` |
| Google Sheets OAuth2 | Google Sheets (OAuth2) | Scope: `spreadsheets` |
| Telegram Bot API | Telegram API | Your bot token |

### 8d. Set n8n Environment Variables
In the n8n UI or your server's `.env`:
```
SHEETS_ID=your_spreadsheet_id
TELEGRAM_CHAT_ID=your_chat_id
PIPELINE_WEBHOOK_URL=http://your-bot-server:8000/webhook/prep
```

### 8e. Activate the Workflow
Click the **Active** toggle on the imported workflow. It will now poll Gmail every 30 minutes and:
- Classify emails: `INTERVIEW_SCHEDULED` / `OFFER_RECEIVED` / `REJECTED` / `APPLIED`
- Update Google Sheets status automatically
- Send Telegram notification for each update
- Trigger interview prep generation when an interview is detected

---

## Scheduled Runs (Cron)

Set the pipeline to run automatically every 6 hours:

```bash
crontab -e
```

Add:
```cron
0 */6 * * * cd /path/to/jobai && .venv/bin/python scripts/run_pipeline.py >> logs/cron.log 2>&1
```

---

## Troubleshooting

### `CookieExpiredError: Session cookies missing or expired for linkedin`
Portal session has expired. Re-export:
```bash
node tools/export-cookies.js
```

### `Gemini API rate limit — falling back to Groq`
This is expected behaviour. Groq (free tier) is the automatic fallback. If Groq also fails, wait a few minutes and retry. You can increase Gemini quota at [aistudio.google.com](https://aistudio.google.com).

### `PDF microservice is not running`
```bash
# Check if containers are up
docker compose ps

# Restart
docker compose up -d pdf-service submitter

# Or run manually (no Docker)
cd services/pdf-service && node index.js &
```

### `COOKIE_SECRET must be at least 32 characters`
Run init_env.sh to regenerate secrets, or manually set in `.env`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### `INTERNAL_TOKEN must be >= 32 chars`
Same as above — generate and set `INTERNAL_TOKEN` in `.env`.

### Google OAuth: `Token has been expired or revoked`
Re-authorise:
```bash
rm ~/.config/ashvani-job-bot/token.json
python scripts/run_pipeline.py --module email
```

### Tests failing with `No module named 'google.generativeai'`
Make sure the venv is activated:
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Security Notes

- **No passwords stored anywhere** — portal auth uses AES-256-GCM encrypted session cookies only
- **All secrets in `.env`** which is git-ignored — never commit it
- **Inter-service calls signed** with HMAC-SHA256 (`INTERNAL_TOKEN`)
- **Resume paths validated** against `RESUME_BASE_DIR` to prevent path traversal
- **Screenshots** written to temp files only — never transmitted over HTTP
- Run `bandit -r . -ll` periodically to scan for new issues

---

## Architecture Reference

```
┌─────────────────────────────────────────────────────┐
│              Python Pipeline Orchestrator            │
│  Module 1: Discovery → Module 2: Resume →           │
│  Module 3: Apply → Module 4: Track → Module 5: Prep │
└──────────┬──────────────────────┬───────────────────┘
           │ httpx + HMAC         │ httpx + HMAC
    ┌──────▼──────┐        ┌──────▼──────┐
    │ PDF Service │        │  Submitter  │
    │ Node+Pptr   │        │  Node+Pw   │
    │  :3001      │        │  :3002      │
    └─────────────┘        └─────────────┘
           │                      │
   Jinja2 HTML→PDF     Stealth Playwright
                        + Cookie Injection

Email Monitoring:  Gmail → n8n (every 30min) → Google Sheets + Telegram
```
