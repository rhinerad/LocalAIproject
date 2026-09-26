# External project-family inventory — 2026-09-22

This note records a targeted consolidation pass from nearby project-family
locations into the canonical tree:

```text
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

No source file outside the canonical tree was moved or deleted.

## Consolidated into this tree

| External source | Canonical copy | Why it was copied |
|---|---|---|
| `A:\Users\rhine\Documents\Codex\local_agent_health_probe.ps1` | `scripts\diagnostics\local_agent_health_probe.ps1` | Newest small local-agent health probe. Useful for checking ports 8760/8188, `/api/status`, GPU, and Ollama without hunting outside the repo. |
| `A:\Users\rhine\agent-tools\la_health_check.py` | `scripts\diagnostics\la_health_check.py` | Small Python wrapper for process inspection. Useful and low-risk; unlike the transcript dumps it is an actual reusable helper. |
| `A:\Users\rhine\Documents\local_agent_audit_20260901.txt` | `docs\audits\local_agent_audit_20260901.txt` | Stray audit marker; copied so future audit references have a stable in-tree location. |
| `A:\Users\rhine\Desktop\EQUAL_SHARES_GENERATION_LIST\CHATGPT_HANDOFF.md` | `docs\reference\external_handoffs\EQUAL_SHARES_CHATGPT_HANDOFF_2026-08-13.md` | Historical Equal Shares handoff. It is superseded for current work, but useful as evidence/reference and now clearly archived inside the canonical tree. |

## Intentionally not copied wholesale

| External location | Decision |
|---|---|
| `A:\Users\rhine\localagent` | Older v0.1.0 CLI harness and different program. Do not merge into `local_agent/` without an explicit code-review task. |
| `A:\Users\rhine\local-agent-core` and `A:\Users\rhine\local-agent-core-tmpclone` | Public-safe extraction repos. Keep separate from the private canonical tree; use only when working on portfolio/open-source packaging. |
| `A:\Users\rhine\agent-tools` | Contains many large probe transcript dumps. Only `la_health_check.py` was copied. The transcript dump folder should remain external unless a specific transcript is needed as evidence. |
| `work\r98_patch\local_agent` inside the canonical folder | Known stale pre-merge fragment. Do not treat it as authoritative. Main `local_agent/` remains authoritative. A later cleanup may archive or delete it only with explicit operator approval. |
| WireGuard files reported under `A:\Users\rhine\com.local-agent.wireguard-wg0.plist`, `wg-blip-win.*`, and `wg-patch-run.sh` | The exact reported root-level files were not present during this pass. Do not invent replacements; use the documented farm/WireGuard runbooks instead. |

## Current caution

`server.py` may still report the old revision string
`2026-09-07-prompt-pack-full-production-r98` even though the working tree has
later September changes. Treat `/api/status` revision as a stale-process check,
not as a full code freshness guarantee.
