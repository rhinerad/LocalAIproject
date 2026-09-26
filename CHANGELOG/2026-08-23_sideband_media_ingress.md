# Sideband media ingress — 2026-08-23

## What changed

The workstation LXMF bridge now accepts the standard Sideband media fields from
an already paired phone:

- file attachments (`FIELD_FILE_ATTACHMENTS`),
- Sideband image fields (`FIELD_IMAGE`), and
- Sideband microphone/audio fields (`FIELD_AUDIO`).

Every accepted item is written once to
`local_agent/uploads/lxmf/<request-id>/`. Only the absolute path, filename, type,
and byte count enter the persistent conversation. The raw bytes never enter chat
JSON or an LLM prompt.

File attachment extensions classify images, audio, and video before the turn is
sent to the existing local sensory-tool loop. This gives photos/gallery shares
to the vision tool, voice messages to local audio measurement/Whisper, and video
files to the video analysis tools. Models remain on the workstation.

## Security

The bridge checks the paired sender before inspecting or persisting attachment
fields. Unpaired media is refused and not written. Each accepted item is capped
at 75 MB, uses a sanitized basename, and is written with exclusive-create
semantics inside a request-specific directory. An append-only metadata/hash audit
is retained in `runtime/lxmf/attachment_audit.jsonl`; it excludes media bytes and
message content. Remote write/build/memory/render permissions remain default-deny.

## Sideband source

The official `markqvist/Sideband` source was fetched into
`local_agent/vendor_sideband` for a future Android fork. Its existing UI already
offers File Attachment, image attachment and microphone recording, allowing this
first media workflow to use the stock installed app. No Android SDK/NDK,
Buildozer, APK, or model was downloaded or built.

## Verification

- Bridge mock suite: **10/10** passed, including paired image storage with path-
  only chat persistence, media-extension routing, and unpaired attachment refusal.
- Native function-calling suite: **9/9** passed.
- Media-analysis suite: **9/9** passed. The action-extraction capability record
  now also reports a reason, matching the rest of the explicit capability API.
- H3 prompt validator: **124/124 valid**.

## Phone progress updates

The bridge now translates safe agent milestones into normal LXMF status messages:
selected CPU/GPU tier, a sanitized tool name, and tool completion. It deliberately
does not mirror model tokens, raw tool arguments/results, file paths, or partial
reasoning. The bridge test suite includes a regression check that secret tool
arguments/results cannot appear in phone status text.

## Visible model replies

Some local Qwen templates returned a `<think>…</think>` block (or a dangling
closing marker after a preamble) in the visible content stream. `ollama_client`
now filters only an initial explicit thinking block before tokens reach either
the desktop GUI or Sideband. Normal prose remains streamed normally. The native
tool suite includes both complete and split-token reasoning-markup regressions.

## Live status

Text round-trip from stock Sideband is live-verified. Send one image, microphone
message, and video/file attachment after restarting the bridge to live-verify
the three media paths; no model or render starts automatically.
