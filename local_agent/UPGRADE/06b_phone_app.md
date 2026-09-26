# Upgrade 6b — make it a real phone app. Run after 06a.

Paste everything below the line into Claude Code. **No downloads.**

---

Turn the mobile web page from 06a into something that behaves like the ChatGPT
app: installed on the home screen, able to take files from the phone, able to use
the camera and voice. **No Android development, no app store, no downloads** —
this is a Progressive Web App, which Android treats as a real installed app.

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

## Read this first — the constraint that shapes everything

**A browser cannot browse the phone's filesystem.** Android does not permit it,
and no amount of web code changes that. What a browser *can* do is receive files
the operator hands it: through a file picker, through the camera, or through the
Android share sheet.

So "file access on the phone" here means **push, not pull.** The operator shares
or picks a file and it goes to the workstation as an attachment. The agent cannot
go looking through the phone on its own.

Genuine filesystem access needs the native Android app in `ROADMAP.md`. Say so
plainly in the CHANGELOG rather than letting this be mistaken for it. What is
below covers most of what the ChatGPT app actually gets used for.

## The HTTPS catch — read before you start

PWA features (installability, service worker, share target) require a **secure
context**: `https://`, or `http://` on `localhost` / `127.0.0.1`.

- **Over 06a's USB `adb reverse`** the phone connects to `http://127.0.0.1:8760`,
  which **counts as secure**. Everything in this prompt works.
- **Over 06's Tailscale** the address is `http://100.x.x.x`, which does **not**
  count. Service workers and install will be blocked.

The fix for that case is Tailscale's own HTTPS — `tailscale cert` / `tailscale
serve` issues a real certificate for the machine's `*.ts.net` name. Note this in
06 as a dependency, but **build and test everything here over USB first**, where
it just works.

## Job 1 — installable app

Add `local_agent/static/manifest.webmanifest`:

- `name`, `short_name`, `start_url`, `display: "standalone"` so it opens without
  browser chrome
- `theme_color` and `background_color` matching the existing dark palette
- icons at 192 and 512 px, **generated as plain SVG/PNG in the repo** — no
  external asset, nothing fetched

Add a service worker that caches the app shell — HTML, CSS, the icons — so it
opens instantly and shows a clear "workstation unreachable" screen instead of a
browser error when the cable is out or the machine is asleep.

**Never cache API responses.** Conversation state lives on the workstation and
must never be served stale from a phone cache.

Verify Chrome on Android offers "Install app" / "Add to Home screen", and that
launching from the icon opens standalone.

## Job 2 — files from the phone

The attachment button already exists but only accepts text types. Extend it:

- images, PDFs, audio and video from the phone's picker
- **images go to the vision tool**, once a model exists (upgrade 4 built the
  gating; this just supplies the file)
- **audio and video go to transcribe / audio_measure**
- text and code inline as they do now
- show a thumbnail for images, a name and size chip for everything else
- **cap the upload size and say so** — a 4K video over a cable is fine, over
  Tailscale later it is not. Enforce a limit and report it rather than hanging.

Server side: accept binary uploads, write them to `local_agent/uploads/` with the
original name preserved, and pass the **path** to the tools. Do not put binary
into the conversation JSON — store the path and a description.

## Job 3 — the Android share sheet

This is the feature that makes it feel like an app rather than a bookmark.

Add `share_target` to the manifest so the agent appears in Android's share menu.
Then, from any app on the phone — gallery, browser, file manager — the operator
can share a photo, a link or text straight into a conversation.

Add a `POST /api/share` endpoint that receives it, creates or appends to a
conversation, and opens the app on that conversation.

Test all three: shared text, a shared URL, and a shared image.

## Job 4 — camera and voice

**Camera** — an input with `accept="image/*" capture="environment"` opens the
camera directly. One tap, photo, straight into the conversation. That is how a
frame gets from the real world to the vision tool.

**Voice** — record on the phone with `MediaRecorder`, upload the audio, and
transcribe it **on the workstation with whisper**. Do not use the Web Speech API:
it usually sends audio to a cloud service, which defeats the point of this whole
project. Whisper is already on the upgrade-5 download list and runs locally.

Until whisper is installed, the record button must say what is missing and its
size — same honesty rule as upgrade 4. Do not hide the button; a disabled control
that explains itself is better than a missing feature.

## Job 5 — behave like an app

- **notify on completion** — a long generation started on the phone should raise
  a local notification when it finishes, so the operator can lock the screen and
  walk away. Local notification from the service worker; no push server.
- **keep the screen awake during generation** via the Wake Lock API, released
  afterwards
- **pull-to-refresh disabled** in the chat area — it currently fights scrolling
- **safe-area insets** so the composer clears the home indicator and notch
- **back gesture** closes the conversation drawer before leaving the app

## Job 6 — keep the desktop identical

Everything above is additive. The desktop browser experience must not change: no
install prompt nagging, no service worker interfering with development, no layout
shift. Verify by using it on the desktop after the changes.

## Verify

Over the USB connection from 06a:

- [ ] Chrome on Android offers to install it; the icon appears on the home screen
- [ ] launching from the icon opens **standalone**, no browser chrome
- [ ] with the cable unplugged it opens and shows a clear unreachable message,
      not a browser error
- [ ] a photo from the gallery attaches, previews, and reaches the workstation
- [ ] the agent appears in Android's **share sheet**; sharing text, a URL and an
      image each land in a conversation
- [ ] the camera button opens the camera and the photo attaches
- [ ] the record button either transcribes locally or names the missing component
      and its size
- [ ] an oversized file is refused with a clear message, not a hang
- [ ] a notification fires when a long generation completes with the screen locked
- [ ] uploads land in `local_agent/uploads/` with sane names; no binary in the
      conversation JSON
- [ ] the **desktop** experience is unchanged
- [ ] guard rails still refuse; `validate_h3_prompt.py` still **124/124**

## Do not stop

Work through. Stop only when every box is ticked and the `CHANGELOG/` entry is
written — stating clearly that this gives **push-based** file access from the
phone, not filesystem browsing, and that the native app in `ROADMAP.md` is still
what would provide the latter.
