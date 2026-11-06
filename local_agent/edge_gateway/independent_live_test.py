#!/usr/bin/env python3
"""Independent workstation test of the live overlay gateway.

Talks to https://10.90.91.1:8743 (overlay unicast, not loopback) with mTLS,
and http://127.0.0.1:8744 for admin inject/revoke. Does not use Termux.
"""
from __future__ import annotations

import json
import os
import ssl
import sqlite3
import sys
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHONE_HOST = "10.90.91.1"
PHONE_PORT = 8743
ADMIN_HOST = "127.0.0.1"
ADMIN_PORT = 8744
PROMPT = "2+2"
FORBIDDEN_ENV = (
    "REDIS_PASSWORD",
    "FARM_BROKER_URL",
    "FARM_RESULT_BACKEND",
    "FARM_AES",
    "AES_KEY",
    "FARM_REDIS",
)
FORBIDDEN_LOG_SUBSTR = (
    "2+2",
    "synthetic-ok",
    "mutated-bad",
    "REDIS_PASSWORD",
    "FARM_BROKER_URL",
)
LOG_ALLOWED_KEYS = {
    "event", "ts", "device_id", "job_id", "status", "state",
    "prompt_chars", "result_chars", "peer_ip", "http_status", "path", "reason",
}


def _admin(method: str, path: str, body=None, expect=None):
    conn = HTTPConnection(ADMIN_HOST, ADMIN_PORT, timeout=10)
    raw = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"} if raw else {}
    conn.request(method, path, body=raw, headers=headers)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode("utf-8"))
    conn.close()
    if expect is not None and resp.status != expect:
        raise SystemExit(f"ADMIN {method} {path} got {resp.status} want {expect}: {data}")
    return resp.status, data


def _phone(method, path, token, cert, key, ca, body=None):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=str(ca))
    ctx.load_cert_chain(str(cert), str(key))
    conn = HTTPSConnection(PHONE_HOST, PHONE_PORT, context=ctx, timeout=10)
    raw = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Edge-Worker": "termux-powerinfer-contract-v1",
        "Accept": "application/json",
    }
    conn.request(method, path, body=raw, headers=headers)
    resp = conn.getresponse()
    raw_body = resp.read()
    data = json.loads(raw_body.decode("utf-8"))
    conn.close()
    return resp.status, data, raw_body.decode("utf-8")


def dump_process_environ(pid: int) -> dict[str, str]:
    try:
        import psutil  # type: ignore
        return dict(psutil.Process(pid).environ())
    except Exception as exc:
        print(f"psutil environ unavailable: {type(exc).__name__}: {exc}")
    # Windows PEB walk
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
        )
        if not handle:
            raise OSError("OpenProcess failed")

        class PROCESS_BASIC_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("Reserved1", ctypes.c_void_p),
                ("PebBaseAddress", ctypes.c_void_p),
                ("Reserved2", ctypes.c_void_p * 2),
                ("UniqueProcessId", ctypes.POINTER(ctypes.c_void_p)),
                ("Reserved3", ctypes.c_void_p),
            ]

        pbi = PROCESS_BASIC_INFORMATION()
        status = ntdll.NtQueryInformationProcess(
            handle, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), None
        )
        if status != 0:
            raise OSError(f"NtQueryInformationProcess {status}")
        peb = pbi.PebBaseAddress
        ptr_size = ctypes.sizeof(ctypes.c_void_p)
        # PEB.ProcessParameters is at 0x20 (x64)
        params_addr = ctypes.c_void_p()
        nread = ctypes.c_size_t()
        kernel32.ReadProcessMemory(
            handle, peb + 0x20, ctypes.byref(params_addr), ptr_size, ctypes.byref(nread)
        )
        # RTL_USER_PROCESS_PARAMETERS.Environment is at 0x80 (x64)
        env_ptr = ctypes.c_void_p()
        kernel32.ReadProcessMemory(
            handle,
            params_addr.value + 0x80,
            ctypes.byref(env_ptr),
            ptr_size,
            ctypes.byref(nread),
        )
        buf = (ctypes.c_wchar * 32768)()
        kernel32.ReadProcessMemory(
            handle, env_ptr, buf, ctypes.sizeof(buf), ctypes.byref(nread)
        )
        kernel32.CloseHandle(handle)
        raw = ctypes.wstring_at(buf, 32767)
        env = {}
        for part in raw.split("\x00"):
            if not part or "=" not in part:
                continue
            k, _, v = part.partition("=")
            env[k] = v
        return env
    except Exception as exc:
        print(f"PEB environ unavailable: {type(exc).__name__}: {exc}")
        return {}


def main() -> int:
    evidence: dict = {"ok": True, "steps": []}
    repo = ROOT
    data_dir = repo / "local_agent" / "edge_gateway" / "runtime"
    tmp = data_dir / "independent_test_client"
    tmp.mkdir(parents=True, exist_ok=True)
    listen_log = Path(
        r"A:\Users\rhine\.grok\sessions\A%3A%5CUsers%5Crhine\01a06ffb-45e9-7550-b95e-0340db61e68c\terminal\call-c5996607-ecb7-4b8b-a5e0-fa30e08b67a5-206.log"
    )
    log_offset = listen_log.stat().st_size if listen_log.is_file() else 0

    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 46176
    cmdline = ""
    try:
        import subprocess
        out = subprocess.check_output(
            [
                "powershell", "-NoProfile", "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
            ],
            text=True,
        ).strip()
        cmdline = out
    except Exception as exc:
        cmdline = f"<unavailable {exc}>"

    environ = dump_process_environ(pid)
    env_keys = sorted(environ.keys())
    env_hits = {k: "<redacted-present>" for k in FORBIDDEN_ENV if k in environ}
    evidence["process"] = {
        "pid": pid,
        "command_line": cmdline,
        "env_key_count": len(env_keys),
        "forbidden_env_present": env_hits,
        "env_keys_sample": [k for k in env_keys if "FARM" in k.upper() or "REDIS" in k.upper() or "AES" in k.upper() or "CELERY" in k.upper()],
    }
    cwd_env_files = []
    for p in (
        repo / "local_agent" / "worker_farm" / ".env",
        repo / "local_agent" / "worker_farm" / ".env.mac_worker.generated",
        repo / "local_agent" / "worker_farm" / "runtime" / "redis-acl",
    ):
        cwd_env_files.append({"path": str(p), "exists": p.exists()})
    evidence["farm_secret_paths"] = cwd_env_files
    if env_hits:
        evidence["ok"] = False
        evidence["steps"].append({"name": "env_dump", "pass": False, "detail": env_hits})
    else:
        evidence["steps"].append({"name": "env_dump", "pass": True, "detail": "no forbidden env keys"})

    # sockets
    import socket
    sock_ev = {}
    for addr, port in (("10.90.91.1", 8743), ("127.0.0.1", 8744), ("0.0.0.0", 8743)):
        s = socket.socket()
        s.settimeout(2)
        sock_ev[f"{addr}:{port}"] = s.connect_ex((addr, port))
        s.close()
    evidence["sockets"] = sock_ev
    if sock_ev.get("10.90.91.1:8743") != 0 or sock_ev.get("127.0.0.1:8744") != 0:
        evidence["ok"] = False
        evidence["steps"].append({"name": "sockets", "pass": False, "detail": sock_ev})
    elif sock_ev.get("0.0.0.0:8743") == 0:
        evidence["ok"] = False
        evidence["steps"].append({"name": "sockets", "pass": False, "detail": "0.0.0.0:8743 connected"})
    else:
        evidence["steps"].append({"name": "sockets", "pass": True, "detail": sock_ev})

    # oversized inject
    st, body = _admin("POST", "/v1/admin/jobs", {"prompt": "x" * 12001, "max_tokens": 8})
    over = st == 400 and "prompt" in json.dumps(body).lower()
    # reject means 400; body may mention 'prompt exceeds' which is policy text not the injected payload
    over_ok = st == 400 and "exceeds" in json.dumps(body)
    evidence["steps"].append({
        "name": "oversized_inject",
        "pass": over_ok,
        "http": st,
        "body": body,
    })
    if not over_ok:
        evidence["ok"] = False

    # enroll workstation test device (not pixel1)
    st, created = _admin("POST", "/v1/admin/devices", {"device_id": "ws-indep-1"}, 201)
    token = created["token"]
    cert = tmp / "ws-indep-1.cert.pem"
    key = tmp / "ws-indep-1.key.pem"
    ca = tmp / "ca.cert.pem"
    cert.write_text(created["client_cert_pem"], encoding="ascii")
    key.write_text(created["client_key_pem"], encoding="ascii")
    ca.write_text(created["ca_cert_pem"], encoding="ascii")
    evidence["steps"].append({
        "name": "enroll",
        "pass": created.get("delivery") == "usb_adb_only",
        "device_id": created.get("device_id"),
        "token_len": len(token),
    })

    # happy path inject
    st, job = _admin("POST", "/v1/admin/jobs", {"prompt": PROMPT, "max_tokens": 8}, 201)
    job_id = job["id"]
    evidence["steps"].append({
        "name": "inject",
        "pass": job.get("kind") == "edge_text_inference" and job.get("prompt_chars") == 3,
        "job_id": job_id,
        "prompt_chars": job.get("prompt_chars"),
        "http": st,
    })

    # claim 1
    st1, claim1, raw1 = _phone(
        "POST", "/v1/edge/jobs/claim", token, cert, key, ca,
        {"capabilities": ["*", "distill", "edge_text_inference"]},
    )
    job_obj = claim1.get("job") or {}
    claim1_ok = (
        st1 == 200
        and job_obj.get("id") == job_id
        and job_obj.get("kind") == "edge_text_inference"
        and job_obj.get("prompt") == PROMPT
        and "https://10.90.91.1:8743"  # URL used below
    )
    evidence["steps"].append({
        "name": "claim1",
        "pass": st1 == 200 and job_obj.get("id") == job_id and job_obj.get("prompt") == PROMPT,
        "http": st1,
        "job_id": job_obj.get("id"),
        "kind": job_obj.get("kind"),
        "phone_url": f"https://{PHONE_HOST}:{PHONE_PORT}/v1/edge/jobs/claim",
    })
    if not (st1 == 200 and job_obj.get("id") == job_id):
        evidence["ok"] = False

    # claim 2 during lease
    st2, claim2, _ = _phone(
        "POST", "/v1/edge/jobs/claim", token, cert, key, ca,
        {"capabilities": ["edge_text_inference"]},
    )
    job2 = claim2.get("job") or {}
    lease_ok = st2 == 200 and job2.get("id") == job_id
    evidence["steps"].append({
        "name": "claim2_same_lease",
        "pass": lease_ok,
        "http": st2,
        "job_id": job2.get("id"),
        "behavior": "idempotent_return_same_job",
    })
    if not lease_ok:
        evidence["ok"] = False

    # complete
    stc, done, _ = _phone(
        "POST", f"/v1/edge/jobs/{job_id}/complete", token, cert, key, ca,
        {"id": job_id, "status": "completed", "result": "synthetic-ok"},
    )
    complete_ok = stc == 200 and done.get("result") == "synthetic-ok"
    evidence["steps"].append({
        "name": "complete",
        "pass": complete_ok,
        "http": stc,
        "status": done.get("status"),
        "result_chars": len(done.get("result") or ""),
    })
    if not complete_ok:
        evidence["ok"] = False

    # mutated replay
    stm, mut, mut_raw = _phone(
        "POST", f"/v1/edge/jobs/{job_id}/complete", token, cert, key, ca,
        {"id": job_id, "status": "completed", "result": "mutated-bad"},
    )
    replay_ok = stm == 409
    evidence["steps"].append({
        "name": "mutated_complete",
        "pass": replay_ok,
        "http": stm,
        "body": mut,
    })
    if not replay_ok:
        evidence["ok"] = False

    stg, view = _admin("GET", f"/v1/admin/jobs/{job_id}", expect=200)
    stored_ok = (
        view.get("untrusted") is True
        and view.get("untrusted_result") == "synthetic-ok"
        and "mutated-bad" not in json.dumps(view)
    )
    evidence["steps"].append({
        "name": "stored_untrusted_first_wins",
        "pass": stored_ok,
        "state": view.get("state"),
        "untrusted": view.get("untrusted"),
        "result_chars": view.get("result_chars"),
        "untrusted_result": view.get("untrusted_result"),
    })
    if not stored_ok:
        evidence["ok"] = False

    # revoke
    st, rev_dev = _admin("POST", "/v1/admin/devices", {"device_id": "ws-indep-revoke"}, 201)
    rtoken = rev_dev["token"]
    rcert = tmp / "ws-indep-revoke.cert.pem"
    rkey = tmp / "ws-indep-revoke.key.pem"
    rcert.write_text(rev_dev["client_cert_pem"], encoding="ascii")
    rkey.write_text(rev_dev["client_key_pem"], encoding="ascii")
    _admin("POST", "/v1/admin/devices/ws-indep-revoke/revoke", {}, 200)
    strv, rbody, rraw = _phone(
        "POST", "/v1/edge/jobs/claim", rtoken, rcert, rkey, ca,
        {"capabilities": ["edge_text_inference"]},
    )
    revoke_ok = strv == 401 and "job" not in rbody and PROMPT not in rraw and "prompt" not in rraw
    evidence["steps"].append({
        "name": "revoked_claim_401",
        "pass": revoke_ok,
        "http": strv,
        "raw": rraw,
    })
    if not revoke_ok:
        evidence["ok"] = False

    # sqlite: only one completed test job from this inject; no second queued from claims
    db = sqlite3.connect(str(data_dir / "edge_ledger.sqlite3"))
    rows = db.execute(
        "SELECT job_id, kind, state, prompt, untrusted_result FROM jobs"
    ).fetchall()
    db.close()
    evidence["ledger_jobs"] = [
        {
            "job_id": r[0],
            "kind": r[1],
            "state": r[2],
            "prompt_chars": len(r[3] or ""),
            "result_chars": len(r[4] or ""),
            "prompt_is_2plus2": r[3] == PROMPT,
        }
        for r in rows
    ]
    queued = [r for r in rows if r[2] == "queued"]
    evidence["steps"].append({
        "name": "no_second_job_queued",
        "pass": len(queued) == 0,
        "queued_count": len(queued),
        "job_count": len(rows),
    })
    if queued:
        evidence["ok"] = False

    new_logs = []
    if listen_log.is_file():
        data = listen_log.read_bytes()[log_offset:].decode("utf-8", errors="replace")
        for line in data.splitlines():
            line = line.strip()
            if line.startswith("{") and "event" in line:
                new_logs.append(line)
    evidence["gateway_log_lines"] = new_logs
    log_ok = True
    log_fail_reasons = []
    for line in new_logs:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        extra = set(obj) - LOG_ALLOWED_KEYS
        if extra:
            log_ok = False
            log_fail_reasons.append(f"extra keys {extra} in {line}")
        blob = json.dumps(obj)
        for bad in FORBIDDEN_LOG_SUBSTR:
            if bad in blob:
                log_ok = False
                log_fail_reasons.append(f"forbidden {bad!r} in {line}")
        if created["token"] in line or rtoken in line:
            log_ok = False
            log_fail_reasons.append("bearer token in log")
    evidence["steps"].append({
        "name": "logs_ids_and_sizes_only",
        "pass": log_ok,
        "fail_reasons": log_fail_reasons,
        "line_count": len(new_logs),
    })
    if not log_ok:
        evidence["ok"] = False

    out = data_dir / "independent_test_evidence.json"
    # strip tokens from written evidence
    text = json.dumps(evidence, indent=2, sort_keys=True)
    text = text.replace(token, "<redacted-token>")
    text = text.replace(rtoken, "<redacted-revoked-token>")
    out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
