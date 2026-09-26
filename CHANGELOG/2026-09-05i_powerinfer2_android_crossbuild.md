# 2026-09-05i — PowerInfer-2 Android sparse runtime cross-build (host only)

Date: 2026-09-05. Host: DuranGamingPC / WSL2 Ubuntu 24.04 x86_64. Id from
`python scripts/next_changelog_id.py`: **2026-09-05i**.

## Why

TODO Step 1 of `docs/POWERINFER2_MOBILE_EDGE_PLAN_2026-08-29.md`: cross-build
the upstream SmallThinker/PowerInfer-2 Android sparse runtime on an x86_64
Linux/WSL host and record hashes. No phone, no Termux compile, no GPU, no
farm, no Equal Shares, no ComfyUI.

## What shipped

- Replay script: `scripts/crossbuild_powerinfer2_android.sh`
- Hash record: `docs/POWERINFER2_CROSSBUILD_2026-09-05.md` (plan doc not
  overwritten)
- Artifacts: `artifacts/powerinfer2_android_arm64/2026-09-05/`

Pins actually used (plan had placeholders):

| Item | Value |
|---|---|
| Repo | `https://github.com/Tiiny-AI/PowerInfer.git` |
| Commit | `8bd56d69906c9d2dba4d3bf6899763401e01a9a4` (existing `external/PowerInfer` HEAD; no tag; `main` not pulled) |
| NDK | r27d `27.3.13750724` Linux zip SHA-256 `601246087a682d1944e1e16dd85bc6e49560fe8b6d61255be2829178c8ed15d9` (SHA-1 matched Google LTS table `22105e410cf29afcf163760cc95522b9fb981121`) |
| Target | `aarch64-linux-android34` / `arm64-v8a` / `-march=armv8.6-a` |
| `llama-cli` SHA-256 | `3b902e1c53f5a2c1c6c8fc1268dee0a0e09917cbe154cb006a007c8667ae8349` (65 383 032 bytes, ELF64 AArch64 PIE) |
| `libaio.so.1.0.1` SHA-256 | `2b09131bb414b31e37cfb125054e94979c83b021f356576d246eeb9dbcca1f5f` (dynamic NEEDED) |

liburing was built into the NDK sysroot copy and CMake statically linked it.
Host smoke: `file`/`readelf` only (Android `linker64`; no qemu, no emulator, no
phone). No model/bundle downloaded.

## TODO.md

The Step 1 checkbox is **left unchecked**. The plan does not pin a commit/tag
or NDK version; this session chose the local clone SHA and NDK r27d LTS and
recorded them. Operator acceptance of those two choices is still required
before treating the pin as the plan's "exact" pin.

## Not changed

Plan doc, Termux worker, Redis/WireGuard farm, Equal Shares, ComfyUI, GPU,
Pixel hardware.
