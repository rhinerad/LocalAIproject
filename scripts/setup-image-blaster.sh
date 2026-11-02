#!/usr/bin/env bash
# Installs or updates image-blaster into tools/image-blaster (macOS / Linux / Git Bash).
# Usage: bash scripts/setup-image-blaster.sh
set -euo pipefail

REPO_URL="https://github.com/neilsonnn/image-blaster"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/tools/image-blaster"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "MISSING: $1 -- $2"
    MISSING=1
  else
    echo "ok: $1 ($("$1" --version 2>/dev/null | head -n1))"
  fi
}

MISSING=0
need git    "install from https://git-scm.com/downloads"
need node   "install Node.js 18+ from https://nodejs.org (LTS)"
need bun    "install with: curl -fsSL https://bun.sh/install | bash"
need claude "install with: curl -fsSL https://claude.ai/install.sh | bash"
if [ "$MISSING" -eq 1 ]; then
  echo
  echo "Install the missing tools above, open a NEW terminal, and run this script again."
  exit 1
fi

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt 18 ]; then
  echo "Node $NODE_MAJOR is too old; image-blaster needs Node 18+ (built-in fetch)."
  exit 1
fi

if [ -d "$DEST/.git" ]; then
  echo "Updating existing image-blaster in $DEST"
  git -C "$DEST" pull --ff-only
else
  echo "Cloning image-blaster into $DEST"
  mkdir -p "$(dirname "$DEST")"
  git clone "$REPO_URL" "$DEST"
fi

cd "$DEST"
chmod +x .claude/hooks/*.sh 2>/dev/null || true
mkdir -p input worlds

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created $DEST/.env -- open it and paste your API keys."
fi

echo "Installing viewer dependencies (bun install)..."
bun install

echo
CLAUDE_PROJECT_DIR="$DEST" bash .claude/hooks/setup-check.sh || true
echo
echo "Done. Next:"
echo "  1. Put your keys in $DEST/.env  (WORLD_LABS_API_KEY, FAL_KEY)"
echo "  2. cd \"$DEST\" && claude"
echo "  3. Drop an image in input/ and say: blast it and confirm each step with me"
