# 2026-11-05a — launcher exit code 1 becomes diagnosable; running the agent no longer dirties the tree

Follow-up to the two out-of-scope observations in `CHANGELOG/2026-11-04a`
section 7 (branch `claude/jolly-dirac-9impbq`). Id claimed with
`scripts/next_changelog_id.py`.

## 1. Launcher: the error is now kept, not cut off

Observation: `START_LOCAL_AGENT_GUI.ps1` came up and exited with code 1 about a
minute after start, before any prompt, with the error truncated by the
console. The root cause is **not established** by this entry; what is
established is why it could not be read, and that is fixed.

How the launcher ends: `python router.py`, `python build_knowledge_pack.py`
(the retrieval rebuild is the slow step, which is where "about a minute"
goes), start the media watcher, then `python server.py` in the foreground.
`server.py` only ever returns 0 (clean stop, or "already running" on the
named mutex) or 2 (`static/index.html` missing); an exit code 1 can only be an
uncaught Python exception, most plausibly in `router.status()` or at the
`ThreadingHTTPServer` bind. Its traceback went to the console and was lost.

Changes:

- `local_agent/server.py`: the `__main__` block wraps `main()`; any uncaught
  exception is printed as before **and** written to
  `local_agent/runtime/launcher/server_crash_<timestamp>.log` (python
  version, cwd, full traceback) before exiting 1. `KeyboardInterrupt` and
  `SystemExit` pass through unchanged. Nothing else in the server changed.
- `local_agent/START_LOCAL_AGENT_GUI.ps1`: after `server.py` returns it
  prints `server.py exited with code N`, names the newest
  `server_crash_*.log` and echoes its last 25 lines, then `exit`s with that
  code (previously the script simply fell off the end). All launcher-written
  logs (`ollama_cpu*.log`, `ollama_gpu*.log`, `media_watcher*.log`) now go to
  `local_agent/runtime/launcher/` instead of next to the code; the "did not
  start" hint names the new path. `runtime/` was already git-ignored.
- `local_agent/README.md`: the "ollama not running" row points at the new log
  location; two new rows cover the exit-code-1 message and a dirty
  `git status` after a launch.

Evidence (this Linux session): with a dummy listener holding `127.0.0.1:8760`,
`python local_agent/server.py` exits 1, prints the `OSError: [Errno 98]
Address already in use` traceback, and leaves
`local_agent/runtime/launcher/server_crash_20261105_164633.log` containing the
same traceback with the `python 3.13.18  cwd ...` header; `git status` stays
clean because the directory is ignored. `python -m py_compile
local_agent/server.py` passes. The PowerShell changes are read-only edits to
the tail of the script and could not be executed here (no `pwsh`); the
workstation reproduction is the next step (section 3).

## 2. Generated files and lock handles are no longer tracked

Observation: one server run rewrote four tracked files
(`local_agent/knowledge/EQUAL_SHARES_REFERENCE.md`, `PROJECT_STATE.json`,
`retrieval_index.json`, `local_agent/media_watcher.log`) and added untracked
`local_agent/chats/*.json` and `*.lock` files.

Why: `build_knowledge_pack.py` rewrites the reference, `PROJECT_STATE.json`
(with a `generated` timestamp) and the 9 MB BM25 index on every launch;
`retrieval.py` rewrites the embedding cache on demand; the launcher's
`-RedirectStandardOutput` rewrote the watcher log; `store.py` creates a
`.lock` file per chat for `process_lock`. All of these were committed by the
initial blanket import (`4d9cf7f`), so every run left them modified.

Changes:

- `.gitignore`: new block for `local_agent/knowledge/EQUAL_SHARES_REFERENCE.md`,
  `PROJECT_STATE.json`, `retrieval_index.json`, `retrieval_embeddings.json`,
  `knowledge/*.tmp`, `knowledge/.fuse_hidden*` (five FUSE leftovers from the
  import) and `local_agent/chats/*.lock`. Checked with `git check-ignore -v
  --no-index`: each of those matches, while `knowledge/SYSTEM_PROMPT.md` and
  the chat `.json` transcripts do **not** (a chat can hold the only record of
  a decision; they stay visible to git on purpose).
- Launcher logs moved to the ignored `runtime/launcher/` (section 1), so the
  historical `local_agent/*.log` files stay tracked but are never rewritten
  again.

**Still required, once, on the workstation** (a `.gitignore` rule does not
untrack a file that is already committed, and the cloud session cannot push a
deletion that would also delete the workstation's working copies). From the
gateway worktree after pulling this commit:

    git rm --cached local_agent/knowledge/EQUAL_SHARES_REFERENCE.md local_agent/knowledge/PROJECT_STATE.json local_agent/knowledge/retrieval_index.json local_agent/knowledge/retrieval_embeddings.json
    git rm --cached local_agent/knowledge/.fuse_hidden0000001a00000001 local_agent/knowledge/.fuse_hidden0000001a00000002 local_agent/knowledge/.fuse_hidden0000001a00000003 local_agent/knowledge/.fuse_hidden0000001a00000004 local_agent/knowledge/.fuse_hidden0000001a00000005
    git rm --cached local_agent/chats/*.lock
    git commit -m "Untrack generated knowledge files, embedding cache, FUSE leftovers and chat lock files"
    git push -u origin claude/jolly-dirac-9impbq

`--cached` removes the index entries only; every working file stays on disk.
Other checkouts of this branch (the `wip/october-2026` tree, if it is ever
rebased onto it) will see those files deleted on checkout and must run
`python local_agent\build_knowledge_pack.py` once, which the launcher does on
every start anyway.

After that commit, a launch plus a chat turn leaves `git status` showing only
the new `local_agent/chats/<id>.json` transcript.

## 3. Unverified / next

- The actual cause of the exit code 1 is unknown until the launcher is run
  again on the workstation with this change; the next failure will leave
  `runtime/launcher/server_crash_*.log` (if it is a Python exception) or, if
  no crash log appears, prove it was not one.
- The PowerShell edits were not executed in this session.
- Not touched: the 12 FAIL + 2 ERROR in `test_router_switching` /
  `test_router_status_busy` (2026-11-04a section 3).

## 4. Workstation results (2026-11-05, reported by the workstation agent)

- Section 2's one-time untrack landed as `8b1fe32`: a fast-forward of 24
  index deletions (4 knowledge files, 5 FUSE leftovers, 15 chat lock files)
  and nothing else, verified from the cloud session with `git diff
  --name-status`. Working copies stayed on disk.
- One leftover the list above missed: `local_agent/media_watcher.log` was
  still tracked and had been rewritten by the *old* launcher's log redirect
  during the GUI turn. Its only change was the watcher's own line
  `[watcher] another watcher instance is already running — exiting`, so it
  was restored with `git checkout --`. The new launcher writes that log
  under `runtime/launcher/`, so this cannot recur; the file was briefly
  locked by the still-running watcher until that watcher was stopped.
- After a full launch plus one chat turn, `git status --short` shows only
  the two new `local_agent/chats/<id>.json` transcripts. That is the
  intended end state of section 2.
- Launcher reproduction (section 3): **did not reproduce.** Windows
  PowerShell `5.1.26100.9711`; the launcher ran the routing check, the
  knowledge rebuild and the watcher start, started `server.py`, a browser tab
  opened and connected to 8760, a short `/api/send` turn returned HTTP 200,
  and the server stayed up for roughly ten minutes until it was stopped on
  purpose. No `server_crash_*.log` was written. One capture limitation: the
  operator's console session dropped during a brief workstation disconnect
  while the server kept running, so the launcher's own exit line was not
  observed, and the agent's console capture showed the launcher's
  `Write-Host` lines but none of the Python child output. That second point
  is consistent with how the original error was "cut off": a Python
  traceback printed to that console is invisible to the capture, which is
  exactly what the crash-log file now covers.

Status: the original exit code 1 remains unexplained and unreproduced. The
instrumentation stays in place; if it recurs, `runtime/launcher/
server_crash_*.log` (or its absence) is the first thing to read.
