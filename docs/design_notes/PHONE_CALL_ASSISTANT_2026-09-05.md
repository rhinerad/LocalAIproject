# Design: operator-approved phone-call assistant

| Field | Value |
|---|---|
| **Document** | Deliberate PSTN/cellular call capability (not Sideband, not the scheduler) |
| **Date** | 2026-09-05 |
| **Status** | Scope only — do not build, do not create a provider account, do not dial |
| **TODO** | `TODO.md` “Operator-approved phone-call assistant” |
| **Out of scope here** | Equal Shares/H3, ComfyUI, farm Redis, PowerInfer edge, LXST mesh voice as a substitute for calling a shop |

This is the implementable spec for the TODO item. Same evidence bar as the
judge-pre-score and activity-trace notes: live call sites, not a product
wish.

**There is no clean v1 that places a real call.** The TODO itself says
design and test only after a provider/device routing contract is approved.
Nothing in this tree can open a PSTN or cellular circuit today. A
simulation-and-policy module can exist *after* that contract is chosen; it
is not a silent “just use Sideband” path. Sign-off list is at the end.
None of the recommended defaults authorize implementation.

---

## Overview

The ask is: the local agent prepares and places **ordinary real-world
phone calls** (pharmacy, utility, appointment) under operator control.
That is a new capability with a new failure mode (the agent speaks to a
human who did not pair with this workstation). It must not be smuggled in
as another LXMF tool.

What already exists is **text to the paired phone** and **Reticulum voice
to other Reticulum users**. Neither reaches a NANP/PSTN number. Treating
them as a dialer would violate the TODO’s first sentence.

Honest sequence:

```text
this note (routing contract + policy)
        |
        |  C1–C8 accepted
        v
Phase 1 — call_gate + allowlist + simulated dial (no socket, no Intent)
        |
        |  C1 names a live path
        v
Phase 2 — one routing implementation (provider API *or* phone Intent)
          + live listen/speak/interrupt/end
          + opt-in recording only after legal review
```

Do not skip to Phase 2 because a simulation “looks like” a product.

---

## What exists today (cited) — and why it is not a dialer

### Paired phone = LXMF chat, not a handset API

| Piece | Code | What it actually is |
|---|---|---|
| Transport | `lxmf_agent.py` module docstring (~1–8) | Separate LXMF peer. Converts Sideband messages to GUI history, calls `agent.answer()`, sends the **final text** back. “No model runs on the phone and this module never starts a render.” |
| Bind | ADR 0001 | Desktop HTTP is `127.0.0.1` only (`server.py` `HOST, PORT = "127.0.0.1", 8760`). Phone access is paired LXMF, not LAN HTTP. |
| Pairing | `remote_security.py` (~1–91, `pair` / `GATED_REMOTE_TOOLS`) | 32-hex LXMF destination hash. Phone default: chat + read/sensory. Writes, renders, memory, ComfyUI, Sonic Pi are grant-gated. |
| Phone events | `lxmf_agent.py` `_phone_event` (~446–453) | Status strings only. **No token stream, no tool args, no tool results, no local paths, no media bytes** to the phone. |
| Attachments | `_receive_attachments` / `_attachment_instructions` (~432–444); `SIDEBAND_TIER_B_BUILD.md` | Inbound image/file/audio/video under `uploads/lxmf/<request-id>/`. Camera overlay is still an unbuilt fork. |
| Tool attribution | `tools.call` (~3255–3273) | Injects `__remote_render_identity` / `__remote_media_*` / `__remote_schedule_identity` **below the model**. The model cannot name a recipient. |

A future call tool that let the model pass a destination number in JSON
would be a regression against that injection seam.

### Phone scheduler = repeating **text** to **the caller**

| Piece | Code |
|---|---|
| Store | `phone_scheduler.py` (~1–8, `create` ~96–118) | Paired identity + 1–500 char template + interval/count. Not audio. |
| Recipient | `tools._schedule_identity` (~2118–2124); catalog text (~2182) | **Phone-only.** Desktop is refused. “the recipient is always the caller and cannot be changed.” |
| Dispatch | `lxmf_agent.drain_scheduled` / `_scheduled_send` (~213–237) | Queues LXMF. Radio delivery is **not** claimed (`phone_scheduler` docstring ~6–8; `radio_metrics.py` ~3–8). |
| Cancel | `_cancel_active_phone_schedules` (~481–487) | Verified sender cancels **its own** jobs only. |
| Audit | `phone_schedule_audit.jsonl` (`_audit` ~72–86) | `job_id`, identity, counter, **message sha256 + char count**, not the plaintext body. |

This is the opposite of “call an arbitrary number.” Extending
`schedule_phone_messages` to dial would also break the “cannot name a
recipient” rule.

### Sideband voice = LXST over Reticulum, not the PSTN

`vendor_sideband/README.md` (~8, ~20): Sideband is an LXMF **and LXST
telephony** client. Calls are “secure and self-sovereign … over
Reticulum.” `vendor_sideband/libs/lxst/README.md` (~42): early alpha;
`rnphone` is Reticulum telephony.

The other party in an ordinary real-world task (clinic, bank, landlord)
does not run Reticulum. LXST cannot satisfy this TODO. Using it would
also impersonate a mesh identity as if it were a NANP caller ID.

The Android companion TODO (immediately under this one) is still
**files/APK**, not `CALL_PHONE`. Stock Sideband “does not use any Android
APIs … dependent on Google” (`vendor_sideband/README.md` ~60–63) and has
no cellular-dial path in this tree.

### Approval UX we can copy (policy), not reuse as-is

| Gate | Pattern | Why not reuse blindly |
|---|---|---|
| `gpu_gate.py` | Sidebar cards; `ask` / `allow` / `block`; one-shot `approved_keys` (~68–117); `/api/gpu_gateway` (`server.py` ~406–529) | **`allow` is blanket GPU permission.** A call gate must not have an “always dial” mode. |
| `file_edit_gate.py` | One-shot hash of exact path+content (~16–35) | Right shape for “this destination + this script + this purpose.” |
| `three_d_contract.py` | `status: approved`, `approved_by`, checksum-pinned workflow; no submit (~23–40) | Right shape for the **routing contract** file. |
| Remote grants | `CHANGELOG/2026-08-26_phone_tool_grants.md` | Per-identity, revocable, audited. A future `place_call` tool belongs in `GATED_REMOTE_TOOLS` from day one (the `render_story_image` miss was a real bug — `TODO.md` ~1145–1152). |

### Encryption we already chose for sensitive blobs

`docs/ENCRYPTED_ARCHIVAL_RUNBOOK.md`: restic, AES-256 + Poly1305-AES,
operator-held recovery secret, never in git/chat. Opt-in call recordings
would be this class, not `chats/*.json`. Phone identity keys are already
on the “never include by default” list (~26–28).

ADR 0004 (explicit-feedback-only learning): call audio/transcripts must
not silently enter memory, exemplars, or `learning.record`.

---

## Routing contract (the decision that blocks a real dial)

Two live paths. They are not mix-and-match in v1.

### Path P — telephony API (Twilio / Telnyx / similar)

Workstation (or a tiny local daemon) asks a **paid PSTN provider** to
create a call. Typical shape: REST create-call + media stream or
conference so the operator and a TTS agent can both be on the line.

| Need | Why it is heavy here |
|---|---|
| Provider account, KYC, funded number, caller ID | New vendor, money, identity documents. This pass forbids opening one. |
| Inbound webhooks / media WebSocket | `server.py` is loopback-only (ADR 0001). A public webhook is a **new internet listener**, not a Sideband message. A tunnel (ngrok, Cloudflare) is a new credential and a new attack surface. |
| Agent speech | TTS into the PSTN. The far end hears a machine. Must announce that, or it is impersonation (TODO: “do not impersonate the operator or claim to be human”). |
| Operator listen/speak | Conference: operator’s phone or desktop WebRTC + callee + agent. Desktop mic through the GUI is new audio code this repo does not have. |
| Recordings | Usually land on the **provider**. That is a third-party copy of the call, before our restic policy can apply. |
| Failure | Provider outage, STIR/SHAKEN unsigned caller ID, spam-label on the far end. |

**Fits:** far-end is any NANP number on the allowlist; operator can stay
at the desktop; agent can talk without Android telephony APIs.

**Does not fit:** “no new public listener,” “no new vendor without an
explicit decision,” “phone never gets farm/Redis credentials” culture
(edge-gateway note). A Twilio auth token on the workstation is a new
secret class next to LXMF identity keys.

### Path D — dial through the paired **cellular** phone

The operator’s handset places a GSM/IMS call. The workstation only
instructs, after confirmation.

| Mechanism | What it actually does |
|---|---|
| `ACTION_DIAL` | Opens the system dialer with the number filled. **Operator still taps Call.** Best phone-side confirmation, but the OS screen does **not** show our purpose or script. |
| `ACTION_CALL` + `CALL_PHONE` | Places the call immediately. Equivalent to skipping the final confirmation if the Intent is fired from our app. Do not use this as the only gate. |
| ConnectionService / InCallService | Can overlay in-call UI (mute, hangup, maybe inject audio). Invasive; looks like a default-dialer grab. Conflicts with Sideband’s “raw Android APIs, no Google helper pipelines” stance unless carefully isolated. |
| Accessibility / speaker + workstation TTS | Agent “speaks” by blasting the speaker. Fragile, records poorly, humiliating, and still picks up the room. Not a contract. |

**Fits:** the operator is already on the audio path (listen/speak/end are
the handset UI). No PSTN vendor. Caller ID is the operator’s real number
(honest, but the far end thinks it is the operator personally — stronger
need to announce an assistant if the agent talks).

**Does not fit:** stock Sideband and the current fork have **no** dial
Intent. This needs an Android/PWA or Sideband-fork contract — the **next**
TODO item, not this one. LXMF is store-and-forward: a mid-call
reconfirm over Sideband can arrive after the sensitive question is
already answered. Live control must be **on the call path** (handset UI
or a simultaneous desktop/WebRTC leg), not an LXMF status ping.

`tools.call` today injects identity so the model cannot pick a recipient.
A phone-dial path must keep that: the number comes from the **allowlist
row the operator selected**, not from model JSON.

### Trade-off (for C1, not for an implementer to pick)

| | Path P (API) | Path D (handset) |
|---|---|---|
| Reaches a real shop | Yes | Yes |
| New vendor + public webhook | Yes (violates ADR 0001 unless a **new** local-only media daemon is designed) | No |
| Android fork / `CALL_PHONE` | No | Yes |
| Operator on the audio path by default | Extra conference leg | Native |
| Agent TTS without speaker-phone hacks | Yes | Hard |
| Recording custody | Provider copy first | Device copy first |
| Impersonation risk | Machine voice + our CID | Operator CID + maybe machine voice |
| Works if phone is off / no cell | Yes | No |
| Fits “no implicit Sideband extension” | Clean new module | Easy to botch by stuffing Intents into the LXMF app |

**Recommendation for C1:** do not pick in this note. Phase 1 (simulation)
does not need either. Phase 2 implements **exactly one**. A hybrid
(API places the call, operator’s cell is conferenced in) is a third
contract, not a default.

LXST/Reticulum voice is **not** a third PSTN path.

---

## Confirmation flow before any dial

Copy `file_edit_gate` (exact hash, one-shot), not `gpu_gate` `allow`.

### Allowlist (unknown numbers are a hard miss)

Stored as operator-edited JSON, not model memory. Suggested row:

```json
{
  "id": "contact_pharmacy_main",
  "label": "Neighborhood pharmacy main desk",
  "e164": "+12065550100",
  "approved_purposes": ["hours", "prescription_ready_check"],
  "added_at": "...",
  "added_by": "operator"
}
```

`e164` is the only dialable form. Display always shows **label + last-4**,
never “the number the model extracted from chat.” If the model proposes a
number that is not a row, the tool returns refused (`unknown_number`) and
does not create a pending card.

Adding a row is its own operator edit (desktop file or a dedicated UI),
audited, not a chat “sure add them.”

### Hard blocks (evaluated before a card is shown)

Refuse with a typed code, no pending approval, no dial:

| Code | Match (v1 policy, not a complete legal tariff database) |
|---|---|
| `emergency` | `911`, `112`, `999`, `000`, `911` with country prefix, `N11` except none of them are allowlist-eligible |
| `premium` | NANP `1-900`, `1-976`, `1-700`; known premium prefixes if a table is later signed off |
| `unknown` | Not in the allowlist, or allowlist row purpose does not include this purpose |
| `short_code` | 3–6 digit SMS-style codes |
| `hidden` | Withheld / private / alphanumeric CID as destination |

Do not let an allowlist row named “emergency” bypass this. Emergency and
premium are **un-allowlistable**.

### Pending card (the only thing that can become a dial)

Hash key = SHA-256 of `contact_id + e164 + purpose + script` (same idea as
`file_edit_gate.key`). Changing the script invalidates the card.

Card fields shown on **desktop sidebar** (new `/api/call_gateway`, sibling
of `/api/gpu_gateway` / `/api/file_edit_gateway` — **not** a GPU card):

- Destination **label** and last-4 (full E.164 visible on expand)
- Purpose (short string from a closed enum, not free model prose)
- Full **call script** (operator-editable before approve)
- “This is an assistant calling with the operator on the line” announcement
  checkbox, default **on**
- Recording: default **off**; if on, show the C2 legal warning and require
  a second checkbox
- Approve / Deny / Timeout (no dial)

Phone path for the **same** card: an LXMF **text** summary (label, last-4,
purpose, “approve on the desktop or reply with the exact token”). Because
`_phone_event` cannot send a structured UI, do **not** treat a vague
Sideband “ok” as consent. Use an explicit one-time token (`CALL-APPROVE
<id>`) or desktop-only approve for v1 of the gate. TODO acceptance asks
for “phone and desktop approval paths”; the phone path is **text-token**,
not a fake in-app button in stock Sideband.

Timeout: no dial, audit `result: timeout`. Same as leaving a GPU card
pending — except a call card must **not** remain grantable after the
script ages out (recommend 10 minutes; GPU cards persist until decided
(`gpu_gate.snapshot` comment ~48–52). Calls are more dangerous; expire
them).

`gpu_gate` mode `allow` has **no analogue**. There is no “auto-dial while
I’m out.”

The agent must not claim it is the operator. Script preamble is a fixed
string, not model-authored: identify as an assistant, name the operator,
state the purpose, offer to hand over.

---

## Operator live control (listen / speak / interrupt / end)

This is the requirement that makes a Sideband-only design dishonest.

| Control | Path P | Path D | Simulation (Phase 1) |
|---|---|---|---|
| Listen | Conference or media fork to desktop/handset | Native in-call audio | N/A (no far end) |
| Speak | Operator leg unmuted | Native | N/A |
| Interrupt agent TTS | Cut TTS stream; operator mic takes the mix | If agent is not on the call, interrupt is just the operator talking | Simulated “barge-in” event |
| End | Hangup API + UI button | Handset end-call + workstation `hangup` that is a no-op if already dead | `end` event closes the sim |

**Phase 1** only tests the **control messages** (interrupt/end/timeout)
against a fake call object. It does not play audio.

**Phase 2** must pick the mix before code:

- If the agent may speak (C4 = yes): there must be a barge-in that
  **stops TTS within one utterance**, not “the operator can send an LXMF
  cancel.” LXMF is too slow for “don’t give them my SSN.”
- If the agent may **not** speak (C4 = no): the capability is
  **click-to-dial with a reviewed script the operator reads**. That is a
  smaller, honest product. Live interrupt of the agent is then vacuous;
  end/listen/speak are the handset. Still needs the dial confirmation and
  mid-call reconfirm for **the agent’s later tools** (e.g. “type this
  confirmation number into the site”) — those tools are not the call
  itself.

Do not impersonate: if C4 = yes, the fixed preamble is mandatory and
not operator-skippable without a separate sign-off (C4b).

---

## Mid-call reconfirmation (not covered by the dial card)

The dial hash is destination + purpose + script. It does **not** cover:

- purchases
- account changes
- sharing sensitive information (address, account numbers, health)
- identity verification (SSN, DOB, full account login)
- any commitment (appointments that cost money, cancellations, legal)

Each is a **new** `file_edit_gate`-shaped card (`call_action_<id>`) with
its own hash. The call stays up; the agent **stops speaking** until
approve/deny/timeout. Timeout = deny. Deny = agent reads a fixed “I
need to stop and check with the owner” line, or silence.

**Never**, even with a card:

- payment credentials (PAN, CVV, expiry, bank password)
- one-time codes (SMS OTP, email OTP, authenticator, “the code we just
  texted you”)
- reading those aloud
- entering them on a keypad / IVR / web form

If the far end asks, the agent must refuse and surface a card that the
operator can **only** dismiss (no “approve send CVV”). Implement as a
closed `forbidden_payload` matcher on the agent’s outbound text and on
any DTMF API. Tests: script containing `4111…` / “the code is 123456”
never reaches the fake send.

The original dial approval is not a standing power of attorney.

---

## Audit model

Default: **minimum metadata**, append-only JSONL, no audio, no
transcript. Pattern: `phone_scheduler._audit` (hash + length, not body)
and `remote_security.audit_tool` (redacted args, remote-only today —
**call audits must also record desktop-originated dials**).

Default row:

```json
{
  "at": 1788.0,
  "call_id": "call_…",
  "destination_id": "contact_pharmacy_main",
  "destination_label": "Neighborhood pharmacy main desk",
  "destination_last4": "0100",
  "purpose": "hours",
  "script_sha256": "…",
  "approval_id": "call_…",
  "approved_by": "desktop|phone-token",
  "result": "completed|canceled|timeout|refused_emergency|refused_premium|refused_unknown|failed",
  "duration_s": 0,
  "recording": "off",
  "transcript": "off",
  "midcall_actions": [{"type": "identity_verification", "result": "denied"}]
}
```

Do **not** store full E.164 in the default row (last-4 + contact id).
The allowlist file already has the number; the audit joins on `destination_id`.

### Recordings / transcripts — opt-in, encrypted, legally loaded

Off by default. Enabling requires C2.

Consent law is **not** a code comment. It varies:

- US **one-party** vs **all-party** jurisdictions (e.g. recording a
  two-person call from Washington or California is not the same as from
  a one-party state).
- The far end’s location may differ from the operator’s.
- A provider-side recording (Path P) is a disclosure to a vendor.
- Announcing “this call may be recorded” is necessary in some places and
  insufficient in others.

**This note is not legal advice.** Phase 2 recordings do not ship until
C2 names a jurisdiction, a notice script, and whether all-party consent
is required. Until then, the only honest default is **no bytes**.

If later enabled:

- Store under the restic class in `ENCRYPTED_ARCHIVAL_RUNBOOK.md`, not
  `chats/`, not LXMF attachments, not `eval_cases/`.
- Separate operator-held key; not the LXMF identity file.
- Retention bound + explicit delete; no silent exemplar mining (ADR 0004).
- Transcripts are as sensitive as audio; same custody.
- Audit row stays `recording: on` + ciphertext id, not a path the model
  can `read_file`.

---

## Phase 1 (the only cut that does not need a live provider)

**Does not dial. Does not open a socket. Does not send an Android Intent.
Does not create a Twilio account.**

Ship only after C1 is at least “Phase 1 only, no live path yet” and C3
(allowlist exists, even if empty).

1. `call_gate.py` — allowlist CRUD (operator file), hard blocks, pending
   cards, expiry, mid-call action cards, forbidden-payload matcher.
2. `place_call` / `hangup_call` / `call_status` tools — **simulated**.
   `place_call` refuses without a granted card. Desktop-only until the
   tool is in `GATED_REMOTE_TOOLS`.
3. `/api/call_gateway` sidebar — destination, purpose, script, approve/
   deny. `APP_REVISION` bump (new API).
4. Append-only `runtime/call_audit.jsonl` with the default row above.
5. Tests (this is the TODO acceptance that can be met **without** a
   carrier): simulated dial/cancel/timeout; refuse 911 / 1-900 /
   unknown; hash change invalidates approval; mid-call purchase without
   a second card is refused; OTP/PAN never leaves the matcher; desktop
   and phone-token approve paths; audit review fixture.

Phone-token approve in Phase 1 can be a **unit-tested** parser without
requiring a live Sideband send (mirror `test_lxmf_bridge.py`’s fake
identity). Live LXMF for call cards is optional and must not be the only
approve path.

**Not Phase 1:** provider SDK, `CALL_PHONE`, WebRTC, TTS into a call,
recordings, GUI “in-call mixer,” LXST.

---

## What would need operator or legal review before any build

| ID | Decision | Recommended default | Why a human |
|---|---|---|---|
| **C1** | Live routing: Path P, Path D, hybrid, or **defer live dial** | **Defer live dial.** Build Phase 1 only if C1 says so. | This is the whole product. P punches ADR 0001; D needs an Android fork that the companion TODO has not approved. |
| **C2** | Recordings/transcripts jurisdiction + notice | **Off.** No bytes until named legal review. | Not a docstring. All-party vs one-party, vendor copies, health/finance calls. |
| **C3** | Allowlist entries | Empty until the operator adds rows by hand | “Unknown numbers” is a hard block; someone must name the pharmacy. |
| **C4** | May the agent speak on the call? | **No** for the first live path (operator reads the approved script) | Impersonation, barge-in latency, TTS quality. C4 = yes is a later contract. |
| **C4b** | If C4 = yes, skippable announcement? | **Not skippable** | TODO: do not impersonate or claim to be human. |
| **C5** | Sideband/Android `CALL_PHONE` / InCallService | **No** until the companion TODO’s routing contract exists | Mixing LXMF identity with cellular dial is a new app, not a tool. |
| **C6** | Public webhook / tunnel for Path P | **No** unless a dedicated local media daemon is designed | Conflicts with ADR 0001. |
| **C7** | New provider account | **No in this pass** (already forbidden) | KYC, billing, STIR/SHAKEN, spam labeling. |
| **C8** | Learning from calls | **Forbidden** (ADR 0004) | Transcripts in Chroma/exemplars would be a silent leak. |

Until C1 is answered, do not add `place_call` to `tools.py`. A simulated
tool without that sign-off still teaches the model that calling exists.

---

## Non-goals

- Extending `schedule_phone_messages` to other people or to audio
- Using LXST as “close enough” to call a business
- `gpu_gate` mode `allow` for dials
- Agent-entered OTPs or card numbers “because the operator approved the call”
- Emergency-services automation
- Shipping a recording feature with a comment instead of C2

---

## Acceptance mapped to live code (and to gaps)

| TODO acceptance | Honest hook |
|---|---|
| Deliberate, not Sideband/scheduler | New `call_gate` module; scheduler stays text-to-self (`tools.py` ~2182, ~3268–3273) |
| Operator-selected recipient, number, objective, script | Allowlist row + hashed card; number not from model JSON |
| Final confirmation of destination + purpose | Sidebar like `file_edit_gate`, **not** `gpu_gate` `allow` |
| Never emergency / premium / unknown | Matcher before the card |
| Listen/speak/interrupt/end | **No live hook today.** Phase 1 simulates events only. Phase 2 needs C1. |
| Min metadata audit; recordings opt-in + encrypted + consent law | JSONL default; restic class; C2 blocks bytes |
| Fresh confirm for purchase / account / sensitive / ID / commitment | Second card type; dial card does not inherit |
| Never payment credentials or OTPs | `forbidden_payload`; no approve-to-send |
| Simulated-call tests, dial/cancel/timeout, audit, phone+desktop approve, refuse prohibited | Phase 1 **if C1 allows Phase 1** |
| Provider/device contract approved first | **C1. Not done.** |

Unverified here: whether any Android `CALL_PHONE` snippet exists outside
`vendor_sideband` (the Sideband README describes LXST only). Treat
cellular Intent support as **absent**.

---

## Key decisions

1. **This is not Sideband and not the phone scheduler.** Those are LXMF
   text (and optional Reticulum voice). Real-world tasks need PSTN or
   cellular.
2. **No clean v1 dial.** Forcing a scope that “dials” would either
   violate ADR 0001 (provider webhook) or the unbuilt Android companion
   contract (handset Intent).
3. **Phase 1 is simulation + gates**, and only after C1 says that Phase
   1 may exist. An empty `place_call` tool is still a behavior change.
4. **One-shot hashed confirmation**, expiry, no blanket allow.
5. **Mid-call actions are a new hash**, never covered by the dial.
6. **Recordings are a legal gate (C2), not a flag in code.** Default off,
   no bytes.
7. **OTP and payment data are un-approvable.**
