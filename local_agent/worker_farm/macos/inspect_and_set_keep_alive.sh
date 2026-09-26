#!/bin/bash
# Run on Louises-MBP. Prints live OLLAMA_KEEP_ALIVE, then (if argv1=apply)
# copies the 30m plist into /Library/LaunchDaemons and reloads the daemon.
set -euo pipefail
echo "=== launchctl environment ==="
launchctl print system/com.local-agent.ollama 2>/dev/null | sed -n '/environment = {/,/}/p' || echo "launchctl print failed"
echo "=== ollama pids ==="
pgrep -lf ollama || true
echo "=== OLLAMA_* from ollama serve ==="
for p in $(pgrep -f '/usr/local/bin/ollama serve' || true); do
  echo "PID=$p"
  ps eww -p "$p" | tr ' ' '\n' | grep -E '^OLLAMA_' || echo "(no OLLAMA_* in ps eww)"
done
echo "=== on-disk plist EnvironmentVariables ==="
plutil -p /Library/LaunchDaemons/com.local-agent.ollama.plist
echo "=== ollama ps ==="
/usr/local/bin/ollama ps || true

if [ "${1:-}" != "apply" ]; then
  exit 0
fi

SRC="${2:-/Users/rhineduran/worker_farm/local_agent/worker_farm/macos/com.local-agent.ollama.plist}"
if [ ! -f "$SRC" ]; then
  echo "missing $SRC" >&2
  exit 1
fi
if ! grep -q 'OLLAMA_KEEP_ALIVE' "$SRC"; then
  echo "source plist missing OLLAMA_KEEP_ALIVE" >&2
  exit 1
fi
echo "=== applying $SRC ==="
# System LaunchDaemon write needs root. kickstart of an already-loaded job
# often works without sudo; the copy does not.
if [ "$(id -u)" -eq 0 ]; then
  cp "$SRC" /Library/LaunchDaemons/com.local-agent.ollama.plist
  chown root:wheel /Library/LaunchDaemons/com.local-agent.ollama.plist
  chmod 644 /Library/LaunchDaemons/com.local-agent.ollama.plist
  launchctl bootout system/com.local-agent.ollama || true
  launchctl bootstrap system /Library/LaunchDaemons/com.local-agent.ollama.plist
  launchctl kickstart -k system/com.local-agent.ollama
else
  echo "not root; trying sudo -n"
  sudo -n cp "$SRC" /Library/LaunchDaemons/com.local-agent.ollama.plist
  sudo -n chown root:wheel /Library/LaunchDaemons/com.local-agent.ollama.plist
  sudo -n chmod 644 /Library/LaunchDaemons/com.local-agent.ollama.plist
  sudo -n launchctl bootout system/com.local-agent.ollama || true
  sudo -n launchctl bootstrap system /Library/LaunchDaemons/com.local-agent.ollama.plist
  sudo -n launchctl kickstart -k system/com.local-agent.ollama || launchctl kickstart -k system/com.local-agent.ollama
fi
sleep 2
echo "=== after apply ==="
launchctl print system/com.local-agent.ollama 2>/dev/null | sed -n '/environment = {/,/}/p'
for p in $(pgrep -f '/usr/local/bin/ollama serve' || true); do
  echo "PID=$p"
  ps eww -p "$p" | tr ' ' '\n' | grep -E '^OLLAMA_' || true
done
