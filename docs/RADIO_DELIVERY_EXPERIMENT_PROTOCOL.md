# Sideband / RNode delivery experiment protocol

This protocol measures **observed** workstation-to-phone delivery. It does not
claim a queued LXMF message was delivered merely because the workstation called
the outbound transport.

## Controlled run

1. Start the existing bridge; do not start a second bridge.
2. From the paired phone, request 20 counter messages at 30-second intervals.
3. On the phone, record every received counter with the phone's Unix timestamp
   or an exported timestamp. Save JSON Lines on the workstation as:

```json
{"job_id":"phone_schedule_example","counter":0,"received_at":1788000000.0}
```

4. After the final wait window, note the workstation Unix close time.
5. Run, without changing any bridge or schedule data:

```powershell
python local_agent\radio_metrics.py --receipts path\to\phone_receipts.jsonl --close-at 1788000900
```

The report calculates observed unconfirmed messages only after `--close-at`.
Without phone receipts it explicitly reports `not_measured_without_phone_receipts`.
Clock skew can distort latency; record it as an experimental limitation unless
both timestamps are synchronized. Do not describe queue events as delivery.
