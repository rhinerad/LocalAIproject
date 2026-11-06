# Upgrade 21 — General assistant and project-scope isolation

## Why this exists

The local agent began as an Equal Shares companion. It is now a general desktop
assistant, but a new unrelated project could still inherit Equal Shares language,
tool suggestions, or prior-chat excerpts. That produces false project-state
claims before the agent has inspected the project actually named by the operator.

## Foundation built — 2026-08-27

- [x] Move the generated Equal Shares handbook to
  `knowledge/EQUAL_SHARES_REFERENCE.md`; it is never the default assistant
  identity.
- [x] Inject that handbook only when the latest request explicitly identifies
  Equal Shares, MiniMax H3, an Equal Shares clip identifier, or an Equal Shares
  path.
- [x] Remove Equal Shares-only tool schemas from ordinary chats. Dispatch stays
  whitelisted and validated regardless of scope.
- [x] Keep Equal Shares prior chats out of general prior-chat retrieval.
- [x] Add regression coverage for general scope, project scope, scoped schemas,
  and prior-chat filtering.

## Workspace selection and inspection built — 2026-08-28

- [x] Add a named workspace/project profile selected explicitly by the operator
  or inferred only from an unambiguous supplied root path.
- [x] Persist the selected workspace separately from the chat model selection;
  changing chats must never silently change the workspace.
- [x] Add a read-only workspace inspection action that reports the root,
  authoritative docs, and detected project type before planning work.
- [x] Add regression fixtures for at least three unrelated projects: a code
  repository, a dataset/LoRA project, and a non-Equal-Shares ComfyUI project.
- [x] Measure false specialist-context activation and false project-tool calls
  in a deterministic scope baseline; future heuristic changes must retain its
  aggregate before/after report.
- [x] Separate general, project, and machine-policy operating memory into
  explicit reviewed sections rather than line filtering once workspace profiles
  exist.
- [x] Add an operator-visible active-workspace indicator and a one-click reset
  to general mode.

## Invariants

- Equal Shares safeguards remain active for actual Equal Shares work.
- A generic mention of ComfyUI, rendering, prompts, clips, video, or audio is
  not sufficient to activate Equal Shares context.
- A prior chat is a continuity hint, never evidence for a new project's state.
- No workspace inference may authorize a render, edit a protected record, or
  weaken tool validation.
