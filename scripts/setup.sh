#!/bin/bash
# ============================================================
# setup.sh — One-time project setup for Ashvani Job Bot
# Run: chmod +x setup.sh && ./setup.sh
# ============================================================

set -e  # Exit on any error

echo "╔══════════════════════════════════════════════════════╗"
echo "║     Ashvani Job Bot — Setup Script                  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# --- 1. Python version check ---
echo "[1/8] Checking Python version..."
python3 --version || { echo "ERROR: Python 3.11+ required"; exit 1; }

# --- 2. Create virtual environment ---
echo "[2/8] Creating virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "  ✓ Virtual environment created"
else
    echo "  ✓ Virtual environment already exists"
fi

source .venv/bin/activate

# --- 3. Install dependencies ---
echo "[3/8] Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  ✓ Dependencies installed"

# --- 4. Install Playwright browsers ---
echo "[4/8] Installing Playwright browsers..."
playwright install chromium
echo "  ✓ Playwright Chromium installed"

# --- 5. Create .env from template ---
echo "[5/8] Setting up environment configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  ✓ .env created from template"
    echo "  ⚠️  IMPORTANT: Edit .env with your real API keys before running!"
else
    echo "  ✓ .env already exists"
fi

# --- 6. Create required directories ---
echo "[6/8] Creating required directories..."
mkdir -p resumes logs data config
chmod 700 resumes  # Restrict access to resume PDFs
echo "  ✓ Directories created"

# --- 7. Set up Google credentials directory ---
echo "[7/8] Setting up credentials directory..."
CREDS_DIR="$HOME/.config/ashvani-job-bot"
mkdir -p "$CREDS_DIR"
chmod 700 "$CREDS_DIR"
mkdir -p "$CREDS_DIR/sessions"
chmod 700 "$CREDS_DIR/sessions"
echo "  ✓ Credentials directory: $CREDS_DIR"
echo "  ⚠️  Place credentials.json at: $CREDS_DIR/credentials.json"

# --- 8. Initialize database ---
echo "[8/8] Initializing database..."
python3 -c "
import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from shared.database import init_db
init_db()
print('  ✓ Database schema initialized')
" 2>/dev/null || echo "  ⚠️  Database init skipped (configure .env first)"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║                Setup Complete!                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys:"
echo "     - GEMINI_API_KEY (https://aistudio.google.com)"
echo "     - GROQ_API_KEY (https://console.groq.com)"
echo "     - TELEGRAM_BOT_TOKEN (BotFather on Telegram)"
echo "     - TELEGRAM_CHAT_ID (your Telegram chat ID)"
echo "     - SHEETS_ID (Google Sheets spreadsheet ID)"
echo ""
echo "  2. Set up Google OAuth:"
echo "     - Download credentials.json from Google Cloud Console"
echo "     - Place at: $HOME/.config/ashvani-job-bot/credentials.json"
echo "     - Run: python scripts/run_pipeline.py --module email"
echo "       (This will open browser for OAuth authorization)"
echo ""
echo "  3. Store portal credentials in keychain:"
echo "     python -c \"import keyring; keyring.set_password('ashvani-job-bot', 'linkedin_email', 'your@email.com')\""
echo "     python -c \"import keyring; keyring.set_password('ashvani-job-bot', 'linkedin_password', 'yourpass')\""
echo ""
echo "  4. Update config/profile.yaml with your details"
echo "  5. Update config/master_resume.yaml with your experience"
echo ""
echo "  6. Test the pipeline:"
echo "     python scripts/run_pipeline.py --dry-run"
echo ""
echo "  7. Schedule with cron (run: crontab -e):"
echo "     0 */6 * * * cd $(pwd) && .venv/bin/python scripts/run_pipeline.py >> logs/cron.log 2>&1"
echo ""
echo "  For security review, read: SEC-AI-Job-Application-Automation-System.md"
