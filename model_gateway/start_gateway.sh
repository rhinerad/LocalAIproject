#!/usr/bin/env bash
# Model gateway preflight (Linux/macOS). No separate gateway process exists:
# the hybrid router lives inside local_agent (Option B). This arms the cloud
# tier for the current shell when sourced with --enable, verifies both Ollama
# tiers, and prints the Claude Code environment block for local-model CLI use.
#
#   bash model_gateway/start_gateway.sh                 # report only
#   source model_gateway/start_gateway.sh --enable      # export MODEL_GATEWAY_CLOUD=1 here
#   bash model_gateway/start_gateway.sh --cloud-check   # one tiny cloud round trip
#   bash model_gateway/start_gateway.sh --strict
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
ARGS=()
for a in "$@"; do
  case "$a" in
    --enable) export MODEL_GATEWAY_CLOUD=1; echo "MODEL_GATEWAY_CLOUD=1 exported for this shell." ;;
    *) ARGS+=("$a") ;;
  esac
done
cd "$ROOT"
"$PY" model_gateway/preflight.py "${ARGS[@]}"
