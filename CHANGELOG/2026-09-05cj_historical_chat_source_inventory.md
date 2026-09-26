# 2026-09-05cj — Historical-chat source inventory (metadata only)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05cj**.

Inventory only. No source selected. No export. `local_agent/chats/`
was listed (names/sizes/dates) and **not opened**.
`sealed_export.py` v1 still synthetic-only (`2026-09-05bj`).
TODO ~513 still blocked on explicit operator source selection.

## Decision menu (do not pick)

Same shape as today’s archive-destination menu: options, coverage,
what is missing. Operator names a source later or names none.

### A. local_agent GUI transcripts (this product)

| | |
|---|---|
| **What** | Runtime storage written by `store.py`: one JSON file per conversation |
| **Where** | `local_agent/chats/*.json` (live) and `chats/_deleted/*.json` |
| **Count / size** | **38** live JSON, **0.6 MB**; **67** deleted JSON, **0.2 MB**. Live mtimes 2026-08-24 → 2026-09-04. Deleted mtimes 2026-08-18 → 2026-08-27. Message counts not taken (would require reading files). |
| **Format** | JSON object: `id`, `title`, `created`, `updated`, `model`, `workspace`, `messages[]` (`role`/`content`). Documented in `store.py`; contents not inspected. |
| **Readable now?** | Yes, by `store.load` / `submit_judge_batch` — **and** a hard refuse for `sealed_export` / distill-without-`--sample`. Using this as a sealed-export source needs the existing TODO decision plus an adapter; v1 will not read it. |

Covers: chats typed in the local-agent GUI only. Does not cover
Claude/Codex/Grok/ChatGPT.com.

### B. Codex CLI / VS Code session logs

| | |
|---|---|
| **What** | OpenAI Codex local session store |
| **Where** | `A:\Users\rhine\.codex\sessions\2026\{05–09}\**\*.jsonl` plus `history.jsonl`, `session_index.jsonl` |
| **Count / size** | **220** session JSONL, **1.80 GB**, 2026-05-01 → 2026-09-04. `history.jsonl` **1.2 MB** (mtime 2026-08-13). `session_index.jsonl` **1.2 KB**. 18 attachment files **0.2 MB**. |
| **Format** | JSONL (Codex session events; typically mixed user/assistant/tool). Not the ChatGPT.com export zip. |
| **Readable now?** | On disk, no ChatGPT-export parser in this repo. Would need a Codex-JSONL adapter before `sealed_export`. `claude-cowork-transcript-imports/` exists and is **empty**. |

Covers: Codex coding sessions on this machine. Does not cover
ChatGPT.com web history unless it was done inside Codex.

### C. Claude Code project transcripts

| | |
|---|---|
| **What** | Claude Code CLI project session JSONL |
| **Where** | `A:\Users\rhine\.claude\projects\` (this handoff tree + `A--Users-rhine\`) and `history.jsonl` |
| **Count / size** | **43** JSONL, **42.0 MB**, 2026-08-09 → 2026-09-03. `history.jsonl` **130 KB** (mtime 2026-09-03). |
| **Format** | JSONL (Claude Code). Desktop Claude `AppData\Local\Claude\logs\` is **9** `.log` files **13.5 MB** — app logs, not a conversations export. |
| **Readable now?** | On disk; no Claude-JSONL adapter in `sealed_export`. Not a Claude.ai account export. |

Covers: Claude Code in these workspaces. Does not cover claude.ai web
chats.

### D. Grok Build TUI sessions

| | |
|---|---|
| **What** | This Grok CLI/TUI session store |
| **Where** | `A:\Users\rhine\.grok\sessions\` |
| **Count / size** | Tree **3847** files **568 MB** (2026-08-25 → 2026-09-05). Of that: **432** `.jsonl` **438 MB**, **746** `.json` **106 MB**, **1955** `.log` **16 MB** (mostly terminal capture). `session_search.sqlite` **2.4 MB**. |
| **Format** | Mix of session JSON/JSONL plus terminal `.log`. |
| **Readable now?** | On disk for the TUI. No adapter in `sealed_export`. |

Covers: Grok Build sessions on this box (including this project).
Does not cover grok.com web history.

### E. Open Interpreter project log

| | |
|---|---|
| **What** | Project-root OI session log |
| **Where** | repo `OPEN_INTERPRETER_SESSION.log` |
| **Count / size** | **1** file **3.4 MB**, mtime 2026-08-20 |
| **Format** | Text log, not chat JSON |
| **Readable now?** | File is readable; would need a log parser. Not a GUI transcript. |

### F. Official ChatGPT.com / Claude.ai data exports — **not on disk**

Downloads/Desktop: no `conversations.json`, no `chatgpt-*.zip` /
`claude-*.zip` data export (only ChatGPT **images** and Claude
**Setup.exe** / prompt markdown). Documents depth-3: no
`conversations.json`.

These would **need a manual export** from chatgpt.com / claude.ai
first. Until then they are not candidates.

The Documents folder named
`referenced-chatgpt-conversation-this-is-an-2` is this **git tree**,
not a ChatGPT export.

### G. CHANGELOG / handoff markdown — **not a chat source**

`CHANGELOG/`, `CHATGPT_HANDOFF.md`, `HANDOFF_STATUS.md` are
engineering notes, not transcripts. Out of this menu.

## What is missing for a real sealed export

1. Operator names one of A–E (or an export produced under F).
2. v1 `sealed_export.py` only seals the distill `--sample` fixture.
   Any real path needs a new allow-list + parser; `chats/` stays
   refused until that decision.
3. No ChatGPT.com or Claude.ai archive is present.

No code, no `chats/` read, no GPU, no distill job.
