# Radio packet-delivery experiment (design only)

**Status:** designed, **not executed**. No packets were sent for this document.
**Purpose:** make LoRa/RNode reliability measurable so portfolio language can
move from “experimental” to “measured prototype” later.

## Hypothesis

A paired RNode link at the recorded profile (914.875 MHz, 500 kHz, SF12, CR 5,
10 dBm) can carry LXMF payloads of known size with a measurable delivery rate
and latency. Bluetooth/USB attachment of the radios is a prerequisite, not the
result.

## What this experiment is not

- Not a Bluetooth pairing test.
- Not a Sideband UI test.
- Not a license to raise power, change band, or flash firmware.
- Not an Equal Shares, ComfyUI, or model-load task.

## Controlled variables

Hold constant across a session:

- both endpoints on the same frequency, bandwidth, SF, CR, and TX power;
- same payload schema (UTF-8, fixed byte sizes);
- same retry policy (zero retries for the raw-loss run; documented retries for
  the application-level run);
- operator notes environment class: indoor-same-room, indoor-through-wall,
  outdoor-line-of-sight.

## Payload sizes

Use synthetic, non-secret payloads only:

| Class | Target size | Why |
|---|---|---|
| Tiny | 32 bytes | Control / keepalive analogue |
| Chat | 256 bytes | Short assistant message |
| Tool | 1024 bytes | One compact tool result |
| Chunk | 2048 bytes | Upper bound before LXMF chunking is expected |

Never put paths, identities, prompts, or media into the payloads.

## Procedure (one environment class)

1. Confirm both radios share the recorded profile. Do not guess missing values.
2. Confirm the desktop HTTP server remains on localhost and is not the transport.
3. Send N=30 packets per size class from phone→workstation, then 30 the other way.
4. Log only: timestamp, direction, size class, sequence number, delivered
   (yes/no), one-way or RTT latency if available, failure mode enum.
5. Repeat on a second day for the same environment class (minimum two sessions
   before quoting a rate).

N=30 is a floor for a first measurement, not a publication-quality sample.

## Metrics to report (aggregates only)

- sample count per direction and size class;
- delivery rate;
- loss rate;
- median and p95 latency for delivered packets;
- failure-mode counts: no-ack, timeout, interface-down, identity-denied,
  payload-too-large, other;
- whether application retries were enabled.

Do not publish RSSI maps, GPS, street addresses, node IDs, or keys.

## Pass language

| Result | Allowed claim |
|---|---|
| Design only | “Experiment designed; not run.” |
| One session | “Preliminary; do not quote a reliability number.” |
| ≥2 sessions, same profile | “Measured prototype under stated conditions.” |
| Bluetooth paired, no packets | **Not** mesh evidence. |

## Blockers before a run

- Phone-side Sideband must actually be using the matching SF12 profile.
- Do not run while a debug Android rebuild holds the phone, or while the
  operator is using the radios for something else.
- Do not run from an agent that cannot see both endpoints.
