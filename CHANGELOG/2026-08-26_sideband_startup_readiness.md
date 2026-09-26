# 2026-08-26 — Sideband bridge startup readiness

- Confirmed the local HTTP agent responds on `127.0.0.1:8760` and both local
  Ollama tiers are healthy.
- Confirmed the LXMF bridge dependencies and paired identities are healthy.
- Increased the Sideband starter's local-agent readiness allowance from 60 to
  150 seconds. Initial local startup can legitimately rebuild the retrieval
  index and recover the watcher before the status endpoint is ready.
- A genuine timeout now directs the operator to the visible launcher window
  instead of suggesting an opaque error inspection path.
