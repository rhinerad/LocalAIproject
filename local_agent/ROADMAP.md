# Local agent — the end goal

**Operator, 2026-08-19:**

> "Im planning on creating a mesh network through using reticulum. The plan is to
> have my phone talk with my computer over this network so that i have a powerful
> local agent that will be able to remotely be an agent on my phone as well as on
> my computer. So the idea is for eventually for us to attach something to the
> local agents gui so that it can connect to another app that we will make for the
> android phone that will enable it to have file access and basically be a chatgpt
> desktop tool that will be available on my computer and phone."

## The shape

```
   phone (Android app)                    workstation
   ┌──────────────────┐                   ┌─────────────────────────┐
   │ chat UI          │                   │ agent.py + tools.py     │
   │ local files      │◀── Reticulum ────▶│ Ollama GPU / CPU tiers  │
   │ camera, mic      │      mesh          │ RTX 5080, project tree  │
   └──────────────────┘                   └─────────────────────────┘
        thin client                          all the compute lives here
```

The phone does **not** run the model. It is a terminal onto the workstation's
agent — which is the whole point, because a 20B MoE and a 16 GB card are not
going in a pocket. The phone contributes what the desktop lacks: camera, mic,
location, and files that only exist on the handset.

## Why Reticulum rather than exposing a port

This matters for decisions being made *now*.

`server.py` binds **127.0.0.1 only**, deliberately — the agent can write project
files and regenerate derived data, so nothing on the network should reach it.
Phone access could be done by binding `0.0.0.0` and hitting it over Wi-Fi, and
that would be the wrong answer: it puts an unauthenticated tool-executing HTTP
server on whatever network the laptop joins.

Reticulum is a better fit for this specific job because it is
**identity-addressed and encrypted end to end by default** — a peer is a
cryptographic identity, not an IP, and it works over whatever transport is
available (TCP, LoRa, packet radio, serial) without any of it being trusted. That
means the phone link can stay secure on a coffee-shop network, and can keep
working with no internet at all, which suits a workflow already built around a
phone hotspot.

**Do not verify this from memory when the time comes.** Reticulum's API surface
and the Android client's capabilities should be checked against current docs
before any code is written — `reticulum.network` and the Sideband client are the
starting points.

## What this implies for work happening now

Design choices to preserve, so the mesh layer is an addition rather than a rewrite:

1. **Keep the HTTP server on 127.0.0.1.** Never bind `0.0.0.0` as a shortcut to
   test phone access. The remote path gets its own transport.
2. **Keep transport separate from agent logic.** `agent.answer()` already takes
   a history list and an event callback and knows nothing about HTTP. That is
   exactly the seam a Reticulum/LXMF transport plugs into — do not let HTTP
   assumptions leak into `agent.py`.
3. **Keep conversations transport-agnostic.** `store.py` writes plain JSON with
   no session or socket concepts. A conversation started on the phone and
   continued on the desktop should be the same file. Add a `source` field on
   messages (`desktop` / `phone`) when the time comes; do not add anything that
   assumes one client.
4. **The tool whitelist becomes more important, not less.** A remote caller
   executing actions on the workstation is exactly why `tools.py` is a fixed
   registry rather than a shell. When the phone can reach it, that property is
   the security model. Never relax it for convenience.
5. **Expect per-identity permissions.** The desktop operator and a remote phone
   should probably not have the same rights — reading state from the phone is
   obviously fine; `write_file` and `run_build` from the phone deserve a
   deliberate decision. Leave room for a permission layer keyed on identity.
6. **Streaming has to survive a slow link.** SSE over a mesh with LoRa in the
   path is a different problem from SSE over localhost. Chunked, resumable
   message delivery will suit it better than a held-open stream. Do not build
   anything that assumes a persistent low-latency socket.

## Rough sequence

| Stage | |
|---|---|
| **now** | Upgrades 1–5. Get the desktop agent genuinely good first — a mesh onto a weak agent is not worth building. |
| next | Extract a transport interface behind `agent.answer()`. Prove it by running the existing GUI through it unchanged. |
| then | Reticulum node on the workstation; a CLI peer on another machine as the first remote client. Prove the link before writing any Android code. |
| then | Android client — chat first, then file access, then camera/mic as agent inputs. |
| later | Per-identity permissions; phone-side capabilities exposed as tools the desktop agent can call. |

## The honest part

The Android app is the largest piece by a wide margin, and it is a real
application rather than a script — packaging, background service, permissions,
and a Reticulum stack on the handset. The Sideband client already exists and does
Reticulum messaging on Android; **checking whether it can be built on, or its
transport reused, is worth doing before writing an app from scratch.**

None of the above has been researched against current documentation. It is a
plan, not a verified design.
