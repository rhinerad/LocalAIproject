# 2026-11-14e — Untrack the agent's memory and the root eval set

Follow-up to 2026-11-14c, found by a fresh-clone check. Untracked
`local_agent/memory.json` and `local_agent/OPERATING_MEMORY.md` (the
agent's stored facts about the operator) and the root copy of
`approved_tasks.jsonl` (explicit-content eval set), and added all three to
`.gitignore`. Replaced the second Windows account's name with
"second-admin" in docs and changelog notes; the ACL script that matches it is
unchanged.

**Before the workstation merges main:** back up `local_agent/memory.json` and
`local_agent/OPERATING_MEMORY.md`, or untrack them there first
(`git rm --cached`), or the merge deletes them and the agent forgets its
stored facts. Same warning as 2026-11-14b and 2026-11-14c.
