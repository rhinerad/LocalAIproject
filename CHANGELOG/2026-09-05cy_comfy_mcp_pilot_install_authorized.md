# 2026-09-05cy — comfyui-mcp + comfy-pilot install authorized (standalone trial)

## Scope

Operator tracking entry, dispatches an install task.

## Context

Operator asked to try https://github.com/artokun/comfyui-mcp (178-tool
MCP server + sidebar agent, "agent-native control plane for ComfyUI")
and https://github.com/AdamPerlinski/comfy-pilot (ComfyUI custom node,
GPLv3, natural-language workflow assistant) directly, standalone --
skipping the research-first compatibility pass offered earlier. Neither
tool has been evaluated against CLAUDE.md's one-backend-ever rule,
Equal Shares evidence-preservation, or the day's catalog-drowning
findings (178 tools is 2.5x the 68-tool schema that caused today's bug)
before this install.

## Operator decision

Install both for standalone/manual trial, not wired into local_agent's
own agent loop or tool schema. Dispatching Purple with explicit
guardrails: one-backend-ever, thermal preflight, no Equal Shares
content/output touches, rollback path preserved for the custom-node
install.

## Status

Dispatching Purple now.
