#!/usr/bin/env bash
# =============================================================================
# scripts/init_env.sh — Secure environment initialiser for Ashvani Job Bot
#
# Responsibilities:
#   1. Auto-generate secure secrets (COOKIE_SECRET, DB_ENCRYPTION_KEY, INTERNAL_TOKEN)
#   2. Create ~/.config/ashvani-job-bot/ with correct permissions
#   3. Copy .env.example → .env with secrets pre-filled
#   4. Interactively collect API keys from the user
#   5. Print a "what's done / what's next" checklist
#
# Idempotent: aborts gracefully if .env already exists.
#
# Usage:
#   chmod +x scripts/init_env.sh
#   ./scripts/init_env.sh
# =============================================================================

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}  ℹ  $*${RESET}"; }
success() { echo -e "${GREEN}  ✓  $*${RESET}"; }
warn()    { echo -e "${YELLOW}  ⚠  $*${RESET}"; }
fatal()   { echo -e "${RED}  ✗  $*${RESET}"; exit 1; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║         Ashvani Job Bot — Environment Setup          ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${RESET}"
echo ""

# ── Locate project root ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
ENV_EXAMPLE="$PROJECT_ROOT/.env.example"
CONFIG_DIR="$HOME/.config/ashvani-job-bot"

# ── Guard: already initialised? ───────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
  warn ".env already exists at $ENV_FILE"
  warn "Delete it first if you want to re-initialise. Exiting."
  echo ""
  exit 0
fi

# ── Prerequisite: openssl ─────────────────────────────────────────────────────
command -v openssl >/dev/null 2>&1 || fatal "openssl not found — install it first."

# ── Step 1: Create config directory ──────────────────────────────────────────
echo -e "${BOLD}[1/5] Creating config directory...${RESET}"
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
mkdir -p "$CONFIG_DIR/resumes"
chmod 700 "$CONFIG_DIR/resumes"
success "Created $CONFIG_DIR (chmod 700)"

# ── Step 2: Generate secure secrets ──────────────────────────────────────────
echo ""
echo -e "${BOLD}[2/5] Generating secure secrets...${RESET}"

COOKIE_SECRET="$(openssl rand -hex 32)"       # 64-char hex → 32 bytes of entropy
DB_ENCRYPTION_KEY="$(openssl rand -hex 32)"   # 64-char hex → 32 bytes
INTERNAL_TOKEN="$(openssl rand -hex 32)"      # 64-char hex → 32 bytes

success "COOKIE_SECRET     generated (64 hex chars)"
success "DB_ENCRYPTION_KEY generated (64 hex chars)"
success "INTERNAL_TOKEN    generated (64 hex chars)"

# ── Step 3: Collect API keys interactively ────────────────────────────────────
echo ""
echo -e "${BOLD}[3/5] API Key collection${RESET}"
echo -e "  ${CYAN}You can press Enter to skip any key and add it to .env manually later.${RESET}"
echo ""

prompt_key() {
  local label="$1"
  local url="$2"
  local var_name="$3"
  echo -e "  ${YELLOW}${label}${RESET}"
  echo -e "  ${CYAN}→ Get it at: ${url}${RESET}"
  read -rp "  Enter value (or press Enter to skip): " _val
  printf '%s' "${_val}"
  echo ""
}

GEMINI_API_KEY="$(prompt_key "GEMINI_API_KEY  (primary LLM)" "https://aistudio.google.com/app/apikey")"
GROQ_API_KEY="$(prompt_key "GROQ_API_KEY    (fallback LLM, free tier)" "https://console.groq.com/keys")"
TELEGRAM_BOT_TOKEN="$(prompt_key "TELEGRAM_BOT_TOKEN  (talk to @BotFather on Telegram)" "https://t.me/botfather")"
TELEGRAM_CHAT_ID="$(prompt_key "TELEGRAM_CHAT_ID    (your chat ID — message @userinfobot)" "https://t.me/userinfobot")"
SHEETS_ID="$(prompt_key "GOOGLE_SHEETS_ID (spreadsheet ID from Sheets URL)" "https://sheets.google.com")"

# ── Step 4: Write .env ────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[4/5] Writing .env...${RESET}"

[[ -f "$ENV_EXAMPLE" ]] || fatal ".env.example not found at $ENV_EXAMPLE"

# Start from the example, then inject all values via sed
cp "$ENV_EXAMPLE" "$ENV_FILE"
chmod 600 "$ENV_FILE"

# Inject auto-generated secrets
sed -i "s|COOKIE_SECRET=your_base64_encoded_32byte_secret_here|COOKIE_SECRET=${COOKIE_SECRET}|g"          "$ENV_FILE"
sed -i "s|INTERNAL_TOKEN=your_hex_encoded_32byte_internal_token_here|INTERNAL_TOKEN=${INTERNAL_TOKEN}|g" "$ENV_FILE"

# Inject user-provided values (only if non-empty)
[[ -n "$GEMINI_API_KEY" ]]       && sed -i "s|GEMINI_API_KEY=your_gemini_api_key_here|GEMINI_API_KEY=${GEMINI_API_KEY}|g"                   "$ENV_FILE"
[[ -n "$GROQ_API_KEY" ]]         && sed -i "s|GROQ_API_KEY=your_groq_api_key_here|GROQ_API_KEY=${GROQ_API_KEY}|g"                           "$ENV_FILE"
[[ -n "$TELEGRAM_BOT_TOKEN" ]]   && sed -i "s|TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here|TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}|g"   "$ENV_FILE"
[[ -n "$TELEGRAM_CHAT_ID" ]]     && sed -i "s|TELEGRAM_CHAT_ID=your_telegram_chat_id_here|TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}|g"           "$ENV_FILE"
[[ -n "$SHEETS_ID" ]]            && sed -i "s|SHEETS_ID=your_google_sheets_spreadsheet_id_here|SHEETS_ID=${SHEETS_ID}|g"                   "$ENV_FILE"

# Set paths to config dir
sed -i "s|COOKIES_PATH=~/.config/ashvani-job-bot/cookies.enc|COOKIES_PATH=${CONFIG_DIR}/cookies.enc|g"         "$ENV_FILE"
sed -i "s|DB_PATH=~/.config/ashvani-job-bot/job_tracker.db|DB_PATH=${CONFIG_DIR}/job_tracker.db|g"             "$ENV_FILE"
sed -i "s|RESUME_BASE_DIR=~/.config/ashvani-job-bot/resumes|RESUME_BASE_DIR=${CONFIG_DIR}/resumes|g"           "$ENV_FILE"
sed -i "s|GOOGLE_CREDENTIALS_JSON=~/.config/ashvani-job-bot/credentials.json|GOOGLE_CREDENTIALS_JSON=${CONFIG_DIR}/credentials.json|g" "$ENV_FILE"

success ".env written to $ENV_FILE (chmod 600)"

# ── Step 5: Checklist ─────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[5/5] Setup checklist${RESET}"
echo ""

check_done() { echo -e "  ${GREEN}[✓]${RESET} $*"; }
check_todo() { echo -e "  ${YELLOW}[ ]${RESET} $*"; }

check_done "Config directory created:    $CONFIG_DIR"
check_done "Secrets auto-generated:      COOKIE_SECRET, DB_ENCRYPTION_KEY, INTERNAL_TOKEN"
check_done ".env created:                $ENV_FILE"

[[ -n "$GEMINI_API_KEY" ]]     && check_done "GEMINI_API_KEY set"       || check_todo "Set GEMINI_API_KEY in .env"
[[ -n "$GROQ_API_KEY" ]]       && check_done "GROQ_API_KEY set"         || check_todo "Set GROQ_API_KEY in .env"
[[ -n "$TELEGRAM_BOT_TOKEN" ]] && check_done "TELEGRAM_BOT_TOKEN set"   || check_todo "Set TELEGRAM_BOT_TOKEN in .env"
[[ -n "$TELEGRAM_CHAT_ID" ]]   && check_done "TELEGRAM_CHAT_ID set"     || check_todo "Set TELEGRAM_CHAT_ID in .env"
[[ -n "$SHEETS_ID" ]]          && check_done "SHEETS_ID set"            || check_todo "Set SHEETS_ID in .env"

check_todo "Download credentials.json → ${CONFIG_DIR}/credentials.json"
check_todo "Run: node tools/export-cookies.js  (exports portal session cookies)"
check_todo "Edit: config/profile.yaml  (your details and job preferences)"
check_todo "Run: docker compose up -d  (start PDF + submitter microservices)"
check_todo "Run: python scripts/run_pipeline.py --dry-run  (smoke test)"

echo ""
echo -e "  ${CYAN}See SETUP.md for the full step-by-step guide.${RESET}"
echo ""
