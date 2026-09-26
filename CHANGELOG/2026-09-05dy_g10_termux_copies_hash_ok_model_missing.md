# 2026-09-05dy — G10 Termux copies hash-verified; --once still blocked on model

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dy**.

No admin inject. No `--once`. Farm `hub.conf` SHA-256 unchanged
`0EA2DF795F5FA8344CDE522FBEC9B22FC3EAA52A2918A724863A4D5B57FC13BC`.

## Overlay recheck

`tun0` still `10.90.91.2/30`. Phone ICMP ping to `10.90.91.1` still
100% loss (Windows Echo Request inbound off). Phone TCP to
`10.90.91.1:8743` still 7 bytes / exit 0. Gateway PID 46176 still
listening.

## Termux home (DocumentsProvider `content read | sha256sum` on device)

Operator inward copy from `2026-09-05dd` is present and matches host:

| Path | SHA-256 |
|---|---|
| `~/.config/local-agent/edge-token` | `74f4303021b46a9e02985d4d18ac11e8e8be806e76169d1dc992811f7b51c699` |
| `~/.config/local-agent/ca.cert.pem` | `b3ba33d94931e5a84134cd31e58b553291aaac55d056e86d5b8f9f399754c104` |
| `~/.config/local-agent/client.cert.pem` | `056402d04bcb419853b116ecd081c4c470d2ed8022a44758dd39dbe6a10b3d55` |
| `~/.config/local-agent/client.key.pem` | `d2c0e11d43b7f87d3f6cb4f3b4cc786ecd16718e0a9af2e63bac0742de12d62a` |
| `~/powerinfer-edge/termux_powerinfer2_edge_worker.py` | `d56f80401a160ea2395a3ae218c8ee6f0605865a838393a7e2c9d2311693c8c0` |
| `~/powerinfer-edge/llama-cli` | `3b902e1c53f5a2c1c6c8fc1268dee0a0e09917cbe154cb006a007c8667ae8349` |
| `~/powerinfer-edge/libaio.so.1` | `2b09131bb414b31e37cfb125054e94979c83b021f356576d246eeb9dbcca1f5f` |

Windows `adb shell content read` without a device-side pipe CRLF-corrupts
PEMs; hashes above are from `content read | sha256sum` **on the phone**.

Staged token/PEMs under Android/data were deleted after this match.
`llama-cli` / worker / `libaio.so.1` leftovers remain (not secrets).
Termux `python` / `python3` exist (`usr/bin`, 4728 bytes). **No GGUF**
in `~/powerinfer-edge`. Host still has no SmallThinker artifact. Did
not download a model. Did not inject. G10 still open.
