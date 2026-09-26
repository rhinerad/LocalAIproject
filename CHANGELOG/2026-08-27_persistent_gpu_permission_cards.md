# 2026-08-27 — persistent GPU permission cards

## Fixed

GPU permission cards were silently removed after 30 minutes. This could make an
operator-approved card appear to have expired, especially after a slow model
load or UI refresh. Pending cards now remain until the operator explicitly
approves or denies them.

Approval remains a one-time grant for the exact workload key; it is not blanket
permission for later GPU work. Repeated clicks on a completed card are now
idempotent and return its original decision instead of reporting an expiry.

## Verification

`python -m unittest local_agent/test_native_tool_calling.py -v`: **27/27
passing**, including persistence of an old pending request, repeat approval, and
single consumption by the matching workload.
