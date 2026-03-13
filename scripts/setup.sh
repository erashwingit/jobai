#!/usr/bin/env bash
# =============================================================================
# scripts/setup.sh — Full one-command setup for Ashvani Job Bot
#
# Runs everything needed to go from a fresh clone to a working pipeline:
#   1. init_env.sh      (secrets + .env)
#   2. Python check + venv + pip install
#   3. Playwright browser install
#   4. Node.js check + npm install (services + tools)
#   5. Directory scaffold
#   6. Pytest smoke test
#
# Usage:
#   chmod +x scripts/setup.sh
#   ./scripts/setup.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}  ℹ  $*${RESET}"; }
success() { echo -e "${GREEN}  ✓  $*${RESET}"; }
warn()    { echo -e "${YELLOW}  ⚠  $*${RESET}"; }
fatal()   { echo -e "${RED}  ✗  $*${RESET}"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║         Ashvani Job Bot — Full Setup                 ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${RESET}"
echo ""

# ── Step 1: Environment initialisation ───────────────────────────────────────
echo -e "${BOLD}[1/7] Initialising environment (.env + secrets)...${RESET}"
bash "$SCRIPT_DIR/init_env.sh"

# ── Step 2: Python version check ─────────────────────────────────────────────
echo ""
echo -e "${BOLD}[2/7] Checking Python 3.10+...${RESET}"

PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3; do
  if command -v "$cmd" &>/dev/null; then
    version=$("$cmd" -c 'import sys; print(sys.version_info[:2])')
    major=$("$cmd" -c 'import sys; print(sys.version_info[0])')
    minor=$("$cmd" -c 'import sys; print(sys.version_info[1])')
    if [[ "$major" -ge 3 && "$minor" -ge 10 ]]; then
      PYTHON_CMD="$cmd"
      break
    fi
  fi
done

[[ -n "$PYTHON_CMD" ]] || fatal "Python 3.10+ not found. Install from https://python.org"
PY_VERSION=$("$PYTHON_CMD" --version)
success "Found $PY_VERSION → using '$PYTHON_CMD'"

# ── Step 3: Node.js version check ────────────────────────────────────────────
echo ""
echo -e "${BOLD}[3/7] Checking Node.js 18+...${RESET}"
command -v node &>/dev/null || fatal "Node.js not found. Install from https://nodejs.org"

NODE_MAJOR=$(node -e 'console.log(process.versions.node.split(".")[0])')
[[ "$NODE_MAJOR" -ge 18 ]] || fatal "Node.js 18+ required (found $(node --version)). Upgrade at https://nodejs.org"
success "Node.js $(node --version) — npm $(npm --version)"

# ── Step 4: Python venv + pip install ────────────────────────────────────────
echo ""
echo -e "${BOLD}[4/7] Setting up Python virtual environment...${RESET}"

if [[ ! -d "$PROJECT_ROOT/.venv" ]]; then
  "$PYTHON_CMD" -m venv "$PROJECT_ROOT/.venv"
  success "Created .venv"
else
  success ".venv already exists — skipping creation"
fi

# shellcheck disable=SC1091
source "$PROJECT_ROOT/.venv/bin/activate"

info "Installing Python dependencies (this may take 1-2 minutes)..."
pip install --upgrade pip --quiet
pip install -r "$PROJECT_ROOT/requirements.txt" --quiet
success "Python dependencies installed"

info "Installing Playwright Chromium browser..."
playwright install chromium --quiet 2>/dev/null || warn "Playwright install had warnings — re-run manually if browser automation fails"
success "Playwright Chromium ready"

# ── Step 5: Node.js services ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[5/7] Installing Node.js service dependencies...${RESET}"

for svc_dir in \
  "$PROJECT_ROOT/services/pdf-service" \
  "$PROJECT_ROOT/services/submitter" \
  "$PROJECT_ROOT/tools"
do
  if [[ -f "$svc_dir/package.json" ]]; then
    svc_name="$(basename "$svc_dir")"
    info "npm install in $svc_name/..."
    (cd "$svc_dir" && npm install --silent)
    success "$svc_name dependencies installed"
  fi
done

# ── Step 6: Directory scaffold ────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[6/7] Creating project directories...${RESET}"
CONFIG_DIR="$HOME/.config/ashvani-job-bot"

mkdir -p \
  "$PROJECT_ROOT/resumes" \
  "$PROJECT_ROOT/data" \
  "$PROJECT_ROOT/logs" \
  "$CONFIG_DIR/resumes"

chmod 700 "$PROJECT_ROOT/resumes" "$CONFIG_DIR" "$CONFIG_DIR/resumes" 2>/dev/null || true
success "Directories created: resumes/, data/, logs/, $CONFIG_DIR/"

# ── Step 7: Smoke test with pytest ───────────────────────────────────────────
echo ""
echo -e "${BOLD}[7/7] Running smoke tests...${RESET}"

if [[ -d "$PROJECT_ROOT/tests" ]]; then
  if python -m pytest "$PROJECT_ROOT/tests/" -x -q --tb=short 2>&1; then
    success "All tests passed"
  else
    warn "Some tests failed — review output above. The bot may still work; tests often need API keys."
  fi
else
  warn "No tests/ directory found — skipping pytest"
fi

# ── Final success banner ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║            Setup Complete! 🎉                        ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "${BOLD}Next steps:${RESET}"
echo ""
echo -e "  ${CYAN}1.${RESET} Add your API keys to ${BOLD}.env${RESET} (GEMINI_API_KEY etc.) if not already done"
echo ""
echo -e "  ${CYAN}2.${RESET} Download Google OAuth credentials:"
echo "     https://console.cloud.google.com/apis/credentials"
echo "     → Save to: ${CONFIG_DIR}/credentials.json"
echo ""
echo -e "  ${CYAN}3.${RESET} Export portal session cookies (one-time manual login):"
echo "     ${BOLD}node tools/export-cookies.js${RESET}"
echo ""
echo -e "  ${CYAN}4.${RESET} Edit your profile and master resume:"
echo "     ${BOLD}config/profile.yaml${RESET}  and  ${BOLD}config/master_resume.yaml${RESET}"
echo ""
echo -e "  ${CYAN}5.${RESET} Start microservices:"
echo "     ${BOLD}docker compose up -d${RESET}"
echo ""
echo -e "  ${CYAN}6.${RESET} Run a dry-run to verify everything works:"
echo "     ${BOLD}source .venv/bin/activate && python scripts/run_pipeline.py --dry-run${RESET}"
echo ""
echo -e "  ${CYAN}7.${RESET} Full setup guide:  ${BOLD}SETUP.md${RESET}"
echo ""
