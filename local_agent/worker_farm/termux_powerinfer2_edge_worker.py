"""Conservative Android edge-worker contract for a future PowerInfer mobile runtime.

This is intentionally *not* a Celery worker and it never connects to Redis.
Giving a mobile device the workstation broker password would let loss of that
device become loss of the entire queue.  Instead it speaks to a future,
per-device authenticated HTTPS edge gateway which exposes only small,
allow-listed inference jobs.

The script is inert by default: --once performs at most one claim.  It does not
download models, start services, render, decrypt farm artifacts, or execute a
shell.  Its API paths are a contract to implement behind the private overlay;
they are not a claim that the gateway exists today.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import ssl
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


MAX_PROMPT_CHARS = 12_000
MAX_RESULT_CHARS = 16_000
MAX_TOKENS = 512
MAX_THREADS = 4
MAX_BODY_BYTES = 262_144
CONTEXT_TOKENS = 512
PROMPT_CHARS_PER_TOKEN = 4
PINNED_GATEWAY_HOST = "10.90.91.1"
ALLOWED_JOB_KINDS = {"edge_text_inference"}
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


class EdgePolicyError(ValueError):
    """Raised before an untrusted remote instruction can reach the runtime."""


@dataclass(frozen=True)
class EdgeConfig:
    gateway: str
    token: str
    binary: Path
    model: Path
    ca_cert: Path
    client_cert: Path
    client_key: Path
    threads: int = 2
    timeout_seconds: int = 300


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _validate_https_gateway(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise EdgePolicyError("edge gateway must be an absolute HTTPS URL")
    host = parsed.hostname.lower()
    loopback = host in {"localhost", "127.0.0.1", "::1"}
    # Loopback is only the adb-reverse path, and only with an explicit cert pin.
    # EDGE_SSL_NO_HOSTNAME is not accepted: it disabled name checks for every host.
    if loopback:
        if not _env_flag("EDGE_ALLOW_LOOPBACK"):
            raise EdgePolicyError(
                "edge gateway must be the private-overlay workstation address, not loopback"
            )
        pin = os.environ.get("EDGE_TLS_PIN_SHA256", "").strip().lower()
        if len(pin) != 64 or any(ch not in "0123456789abcdef" for ch in pin):
            raise EdgePolicyError("loopback gateway requires EDGE_TLS_PIN_SHA256")
    elif host != PINNED_GATEWAY_HOST:
        raise EdgePolicyError("edge gateway must be https://10.90.91.1")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise EdgePolicyError("edge gateway URL must not contain credentials, query, or fragment")
    return url.rstrip("/")


def _require_readable_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise EdgePolicyError(f"{label} is missing")
    try:
        if path.stat().st_size < 32:
            raise EdgePolicyError(f"{label} is missing or implausibly short")
    except OSError as exc:
        raise EdgePolicyError(f"{label} cannot be read") from exc
    return path


def build_config(
    *, gateway: str, token_file: Path, binary: Path, model: Path,
    threads: int, timeout_seconds: int,
    ca_cert: Path | None = None, client_cert: Path | None = None,
    client_key: Path | None = None,
) -> EdgeConfig:
    normalized = _validate_https_gateway(gateway)
    try:
        token = token_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise EdgePolicyError("edge token file cannot be read") from exc
    if len(token) < 24:
        raise EdgePolicyError("edge token is missing or implausibly short")
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise EdgePolicyError("llama executable is missing or not executable")
    if not model.is_file():
        raise EdgePolicyError("approved model file is missing")
    if not 1 <= threads <= MAX_THREADS:
        raise EdgePolicyError(f"threads must be between 1 and {MAX_THREADS}")
    if not 15 <= timeout_seconds <= 900:
        raise EdgePolicyError("timeout must be between 15 and 900 seconds")
    conf_dir = token_file.parent
    ca_path = _require_readable_file(ca_cert or (conf_dir / "ca.cert.pem"), "edge CA certificate")
    cert_path = _require_readable_file(client_cert or (conf_dir / "client.cert.pem"), "edge client certificate")
    key_path = _require_readable_file(client_key or (conf_dir / "client.key.pem"), "edge client key")
    return EdgeConfig(
        normalized, token, binary, model, ca_path, cert_path, key_path,
        threads, timeout_seconds,
    )


def _ssl_context(config: EdgeConfig) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    host = (urlparse(config.gateway).hostname or "").lower()
    # The overlay certificate's SAN is the overlay address. Loopback cannot
    # match that name, so it is allowed only when a fingerprint pin is set.
    ctx.check_hostname = host == PINNED_GATEWAY_HOST
    ctx.verify_mode = ssl.CERT_REQUIRED
    try:
        ctx.load_verify_locations(cafile=str(config.ca_cert))
        ctx.load_cert_chain(str(config.client_cert), str(config.client_key))
    except OSError as exc:
        raise EdgePolicyError("edge mTLS materials cannot be loaded") from exc
    return ctx


def _json_request(
    config: EdgeConfig, method: str, path: str, body: dict[str, Any] | None = None,
    *, phase: str = "claim",
) -> dict[str, Any]:
    payload = None if body is None else json.dumps(
        body, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    if payload is not None and len(payload) > MAX_BODY_BYTES:
        raise EdgePolicyError("edge request exceeds the body limit")
    parsed_url = urlparse(config.gateway)
    host = parsed_url.hostname or ""
    port = parsed_url.port or 443
    pin = os.environ.get("EDGE_TLS_PIN_SHA256", "").strip().lower()
    unavailable = (
        "edge gateway is unavailable; no job was run"
        if phase == "claim"
        else "inference finished; completion was not acknowledged"
    )
    conn = http.client.HTTPSConnection(
        host, port, context=_ssl_context(config), timeout=20,
    )
    try:
        # Python 3.13 clears the peer cert once the response body is read.
        conn.connect()
        peer_der = conn.sock.getpeercert(binary_form=True) if conn.sock is not None else None
        conn.request(
            method, path, body=payload,
            headers={
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "X-Edge-Worker": "termux-powerinfer-contract-v1",
            },
        )
        response = conn.getresponse()
        if pin:
            digest = hashlib.sha256(peer_der).hexdigest() if peer_der else ""
            if digest != pin:
                raise EdgePolicyError("edge gateway certificate pin mismatch")
        if response.status in {301, 302, 303, 307, 308}:
            raise EdgePolicyError("edge gateway redirects are not allowed")
        raw = response.read(MAX_BODY_BYTES + 1)
    except EdgePolicyError:
        raise
    except (http.client.HTTPException, OSError, ssl.SSLError) as exc:
        raise EdgePolicyError(unavailable) from exc
    finally:
        conn.close()
    if len(raw) > MAX_BODY_BYTES:
        raise EdgePolicyError("edge gateway response exceeds the body limit")
    if response.status >= 400:
        raise EdgePolicyError(unavailable)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EdgePolicyError("edge gateway returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise EdgePolicyError("edge gateway response must be an object")
    return parsed


def validate_job(job: dict[str, Any]) -> tuple[str, str, int]:
    job_id = job.get("id")
    if not isinstance(job_id, str) or not _JOB_ID_RE.fullmatch(job_id):
        raise EdgePolicyError("job id is invalid")
    if job.get("kind") not in ALLOWED_JOB_KINDS:
        raise EdgePolicyError("job kind is not approved for the phone")
    prompt = job.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        raise EdgePolicyError("job prompt is empty or exceeds the edge limit")
    requested_tokens = job.get("max_tokens", 256)
    if isinstance(requested_tokens, bool) or not isinstance(requested_tokens, int):
        raise EdgePolicyError("job token budget is outside the edge limit")
    if not 1 <= requested_tokens <= MAX_TOKENS:
        raise EdgePolicyError("job token budget is outside the edge limit")
    room = CONTEXT_TOKENS - requested_tokens
    if room < 1 or len(prompt) > room * PROMPT_CHARS_PER_TOKEN:
        raise EdgePolicyError("job prompt does not fit the runtime context")
    attempt = job.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise EdgePolicyError("job attempt is invalid")
    return job_id, prompt, requested_tokens


def _uses_classic_powerinfer(binary: Path) -> bool:
    if _env_flag("EDGE_USE_CLASSIC_POWERINFER"):
        return True
    name = binary.name.lower()
    return name in {"powerinfer-main", "main"} or "powerinfer" in name


def _uses_stock_llama(binary: Path) -> bool:
    """True for Termux llama.cpp package binaries (GGUF), not PowerInfer CLIs."""
    if _uses_classic_powerinfer(binary):
        return False
    if _env_flag("EDGE_USE_STOCK_LLAMA"):
        return True
    name = binary.name.lower()
    if name == "llama-completion":
        return True
    norm = str(binary).replace("\\", "/")
    return name.startswith("llama-") and "/usr/bin/" in norm


def build_runtime_command(config: EdgeConfig, prompt: str, max_tokens: int) -> list[str]:
    """Return a shell-free command suitable for subprocess.run()."""
    if _uses_stock_llama(config.binary):
        return [
            str(config.binary), "-m", str(config.model),
            "-no-cnv", "-c", str(CONTEXT_TOKENS), "-fit", "off",
            "--temp", "0.3", "--top-k", "20", "--top-p", "0.95",
            "-p", prompt,
            "-t", str(config.threads), "-n", str(max_tokens), "-ub", "4",
        ]
    if _uses_classic_powerinfer(config.binary):
        return [
            str(config.binary), "-m", str(config.model),
            "-c", str(CONTEXT_TOKENS), "--simple-io",
            "--temp", "0.3", "--top-k", "40", "--top-p", "0.95",
            "-p", prompt,
            "-t", str(config.threads), "-n", str(max_tokens), "-ub", "4",
        ]
    return [
        str(config.binary), "-m", str(config.model), "--no-cnv",
        "--temp", "0.3", "--top-k", "20", "--top-p", "0.95",
        "--samplers", "temperature;top_k;top_p", "-p", prompt,
        "-t", str(config.threads), "-n", str(max_tokens),
        "-c", str(CONTEXT_TOKENS), "-ub", "4",
    ]


def run_job(config: EdgeConfig, job: dict[str, Any]) -> dict[str, Any]:
    job_id, prompt, max_tokens = validate_job(job)
    # Keep Termux's normal environment so stock llama backends load.
    # Drop LD_LIBRARY_PATH so PowerInfer libs cannot shadow ggml.
    environment = dict(os.environ)
    environment.pop("LD_LIBRARY_PATH", None)
    if _uses_stock_llama(config.binary):
        environment.setdefault("PREFIX", "/data/data/com.termux/files/usr")
        prefix_bin = str(Path(environment["PREFIX"]) / "bin")
        path = environment.get("PATH", "")
        if prefix_bin not in path.split(":"):
            environment["PATH"] = prefix_bin + (":" + path if path else "")
    else:
        # Sparse / PowerInfer-only extras; never from the queue message.
        for name in ("MAX_N_CACHED", "EXPERT_BUNDLE_PATH"):
            value = os.environ.get(name)
            if value:
                environment[name] = value
    command = build_runtime_command(config, prompt, max_tokens)
    proc = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        env=environment,
    )
    stdout_box: list[str] = []
    stderr_box: list[str] = []
    overflow = threading.Event()

    def _cap(pipe, limit: int, box: list[str]) -> None:
        if pipe is None:
            box.append("")
            return
        chunk = pipe.read(limit + 1)
        if chunk and len(chunk) > limit:
            overflow.set()
            try:
                proc.kill()
            except OSError:
                pass
        box.append((chunk or "")[:limit])

    readers = (
        threading.Thread(target=_cap, args=(proc.stdout, MAX_RESULT_CHARS, stdout_box)),
        threading.Thread(target=_cap, args=(proc.stderr, 8000, stderr_box)),
    )
    for reader in readers:
        reader.start()
    try:
        proc.wait(timeout=config.timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        for reader in readers:
            reader.join(timeout=5)
        return {"id": job_id, "attempt": int(job["attempt"]), "status": "timed_out", "result": ""}
    for reader in readers:
        reader.join(timeout=5)
    if overflow.is_set():
        return {"id": job_id, "attempt": int(job["attempt"]), "status": "refused", "result": "runtime output exceeded the capture cap"}
    result = stdout_box[0] if stdout_box else ""
    if proc.returncode:
        err = stderr_box[0] if stderr_box else ""
        if err:
            print(f"runtime_failed rc={proc.returncode} stderr={err}", flush=True)
        return {"id": job_id, "attempt": int(job["attempt"]), "status": "runtime_failed", "result": ""}
    return {"id": job_id, "attempt": int(job["attempt"]), "status": "completed", "result": result}


def _outbox_dir() -> Path:
    root = Path.home() / ".config" / "local-agent" / "outbox"
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root


def _complete_with_retry(config: EdgeConfig, outcome: dict[str, Any]) -> None:
    delay = 1
    last: Exception | None = None
    for _ in range(6):
        try:
            _json_request(
                config, "POST", f"/v1/edge/jobs/{outcome['id']}/complete",
                outcome, phase="complete",
            )
            return
        except EdgePolicyError as exc:
            last = exc
            time.sleep(delay)
            delay = min(delay * 2, 30)
    raise EdgePolicyError("inference finished; completion was not acknowledged") from last


def _flush_outbox(config: EdgeConfig) -> None:
    for path in sorted(_outbox_dir().glob("*.json")):
        outcome = json.loads(path.read_text(encoding="utf-8"))
        _complete_with_retry(config, outcome)
        path.unlink()


def _remember_outcome(outcome: dict[str, Any]) -> Path:
    job_id = str(outcome.get("id", ""))
    if not _JOB_ID_RE.fullmatch(job_id):
        raise EdgePolicyError("job id is invalid")
    path = _outbox_dir() / f"{job_id}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(outcome), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    return path


def process_once(config: EdgeConfig) -> bool:
    _flush_outbox(config)
    response = _json_request(
        config, "POST", "/v1/edge/jobs/claim",
        {"capabilities": ["edge_text_inference"]}, phase="claim",
    )
    job = response.get("job")
    if job is None:
        return False
    if not isinstance(job, dict):
        raise EdgePolicyError("edge gateway returned a malformed job")
    try:
        outcome = run_job(config, job)
    except EdgePolicyError as exc:
        attempt = job.get("attempt") if isinstance(job.get("attempt"), int) else 1
        outcome = {
            "id": str(job.get("id", "")),
            "attempt": attempt,
            "status": "refused",
            "result": str(exc),
        }
    saved = _remember_outcome(outcome)
    _complete_with_retry(config, outcome)
    saved.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Disabled-by-default Termux PowerInfer edge-worker contract")
    parser.add_argument("--gateway", required=True, help="private-overlay HTTPS gateway; never Redis")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--ca-cert", type=Path, default=None, help="defaults to sibling ca.cert.pem of --token-file")
    parser.add_argument("--client-cert", type=Path, default=None, help="defaults to sibling client.cert.pem of --token-file")
    parser.add_argument("--client-key", type=Path, default=None, help="defaults to sibling client.key.pem of --token-file")
    default_bin = os.environ.get("EDGE_LLAMA_BIN")
    parser.add_argument(
        "--binary", type=Path,
        default=Path(default_bin) if default_bin else None,
        required=not default_bin,
        help="llama-completion (stock GGUF) or PowerInfer llama-cli; or set EDGE_LLAMA_BIN",
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--once", action="store_true", help="claim at most one job (the required initial mode)")
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()
    try:
        config = build_config(
            gateway=args.gateway, token_file=args.token_file, binary=args.binary,
            model=args.model, threads=args.threads, timeout_seconds=args.timeout,
            ca_cert=args.ca_cert, client_cert=args.client_cert, client_key=args.client_key,
        )
        if args.once:
            process_once(config)
            return 0
        if not 15 <= args.poll_seconds <= 3600:
            raise EdgePolicyError("poll interval must be between 15 and 3600 seconds")
        while True:
            worked = process_once(config)
            if not worked:
                time.sleep(args.poll_seconds)
    except EdgePolicyError as exc:
        print(f"edge worker refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
