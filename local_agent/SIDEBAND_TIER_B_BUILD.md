# Sideband Tier B — minimal Android fork build

## What is already working

The checked-in Sideband fork is the upstream source under `vendor_sideband/`,
licensed CC BY-NC-SA 4.0. It builds as the separate Android package
`local.equalshares.sidebandagent` (**Equal Shares Agent**) so it can coexist
with the stock Sideband application. Its existing image/file/audio attachment UI is already
accepted by the paired LXMF workstation bridge. The bridge validates the paired
identity first, writes each accepted item under `uploads/lxmf/<request-id>/`,
and passes only the resulting local path and metadata to the local agent. Phone
tools remain default-denied for writes, builds, memory changes, renders, and
ComfyUI stop.

The Tier-B overlay adds one Android-only **Capture Camera Image** action to the
normal Sideband attachment menu. It requests `CAMERA` at the moment the user
selects the action, captures to Sideband's app cache, and marks it as Sideband's
existing medium-resolution image attachment. It does not introduce HTTP, a new
network listener, a workstation command, or a direct filesystem API.

Normal Sideband status/notification behavior continues to provide completion
messages. The bridge sends only safe status labels and final replies; it never
sends token streams, tool arguments, tool results, local paths, or media bytes
back to the phone.

## Build gate

The fork is not yet compiled. Building needs a Linux/WSL Buildozer environment,
Android SDK/NDK/JDK downloads, and a USB-debug phone validation. Do not build
until the operator approves those downloads. Before building, preserve the
upstream CC BY-NC-SA license and clearly identify the derivative application.

## Required live acceptance after build

1. Install the debug APK on the operator's phone through USB debugging.
2. Verify paired text stays functional and an unpaired sender is refused.
3. Send a gallery image, direct camera image, ordinary file, microphone audio,
   and short video to the paired workstation contact.
4. Verify every accepted item appears only in its request-scoped workstation
   upload folder and triggers the appropriate local media tool.
5. Verify remote attempts to render, write a file, run a build, or stop ComfyUI
   are denied and audited.
6. Verify a normal desktop GUI chat remains unaffected.

## No-model verification

Run:

```powershell
python local_agent\test_sideband_tier_b.py
python local_agent\test_lxmf_bridge.py
```
