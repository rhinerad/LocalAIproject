#!/usr/bin/env python3
"""Record the PowerInfer acceptance-gate checklist: solver/split logs plus cold/warm 20-turn chat.

Does not promote a model to the agent picker. Writes validation/acceptance_gate.json
with hashes, RAM, VRAM, latency percentiles, and tokens/sec. Prompt text is not stored;
only prompt-count and a hash of the committed prompt file.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from pipeline_lib import (  # noqa: E402
    gpu_snapshot,
    host_ram_snapshot,
    parse_powerinfer_logs,
    percentile,
    sha256_file,
    sha256_tree,
    target_config,
    utc_now,
    write_json,
)


def _wait_http(url: str, host: str, port: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last = None
    paths = ("/health", "/", "/healthz")
    while time.monotonic() < deadline:
        try:
            sock = __import__("socket").create_connection((host, port), timeout=2)
            sock.close()
            for path in paths:
                try:
                    urllib.request.urlopen(f"{url}{path}", timeout=2)
                    return
                except Exception as exc:
                    last = exc
            return
        except Exception as exc:
            last = exc
            time.sleep(0.5)
    raise SystemExit(f"server did not become ready at {url}: {last}")


def _stream_completion(url: str, prompt: str, n_predict: int, cache_prompt: bool, stop: list[str] | None = None) -> dict:
    payload = {
        "prompt": prompt,
        "n_predict": n_predict,
        "n_keep": -1,
        "cache_prompt": cache_prompt,
        "stream": True,
        "stop": stop or ["</s>", "<|eot_id|>", "<|end_of_text|>"],
    }
    request = urllib.request.Request(
        f"{url}/completion",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    first_token_s = None
    predicted = 0
    content_parts: list[str] = []
    last = {}
    with urllib.request.urlopen(request, timeout=600) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            try:
                part = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if part.get("content") and first_token_s is None:
                first_token_s = time.perf_counter() - t0
            if part.get("content"):
                content_parts.append(str(part["content"]))
            if part.get("stop"):
                last = part
            predicted = int(part.get("tokens_predicted") or predicted)
    total_s = time.perf_counter() - t0
    timings = last.get("timings") or {}
    predicted_n = int(timings.get("predicted_n") or last.get("tokens_predicted") or predicted)
    predicted_ms = float(timings.get("predicted_ms") or 0.0)
    prompt_n = int(timings.get("prompt_n") or last.get("tokens_evaluated") or 0)
    prompt_ms = float(timings.get("prompt_ms") or 0.0)
    decode_tps = None
    if predicted_ms > 0 and predicted_n > 0:
        decode_tps = predicted_n / (predicted_ms / 1000.0)
    elif predicted_n > 0 and first_token_s is not None and total_s > first_token_s:
        decode_tps = predicted_n / (total_s - first_token_s)
    return {
        "total_s": round(total_s, 4),
        "ttft_s": round(first_token_s, 4) if first_token_s is not None else None,
        "prompt_tokens": prompt_n,
        "completion_tokens": predicted_n,
        "prompt_ms": round(prompt_ms, 3),
        "predicted_ms": round(predicted_ms, 3),
        "decode_tokens_per_sec": round(decode_tps, 3) if decode_tps else None,
        "stopped_eos": bool(last.get("stopped_eos")),
        # Used only to form the immediate next prompt in memory. _run_session
        # removes it before the benchmark receipt is written.
        "content": "".join(content_parts),
    }


def _render_prompt(history: list[tuple[str, str]], user: str, chat_format: str) -> tuple[str, list[tuple[str, str]]]:
    history = history + [("user", user)]
    if chat_format == "llama3":
        prompt = "<|begin_of_text|>"
        for role, text in history:
            prompt += f"<|start_header_id|>{role}<|end_header_id|>\n\n{text}<|eot_id|>"
        prompt += "<|start_header_id|>assistant<|end_header_id|>\n\n"
    elif chat_format == "raw":
        # Base completion models (class: base) receive the prompt verbatim.
        # Instruction templates are meaningless to a model without instruction
        # fine-tuning and cause immediate EOS responses.
        prompt = user
    elif chat_format == "checkpoint_chatml":
        prompt = ""
        for role, text in history:
            if role == "system":
                prompt += f"<|im_start|>system\n{text}<|im_end|>\n"
            elif role == "user":
                prompt += f"<|im_start|>user\n{text}<|im_end|>\n<|im_start|>assistant\n"
            elif role == "assistant":
                prompt += f"{text}<|im_end|>\n"
            else:
                raise ValueError(f"unsupported checkpoint_chatml role: {role!r}")
    else:
        prompt = ""
        for index in range(0, len(history), 2):
            user_text = history[index][1]
            prompt += f"<s>[INST] {user_text} [/INST]"
            if index + 1 < len(history):
                prompt += f" {history[index + 1][1]}</s>"
    return prompt, history


def _summarize(turns: list[dict]) -> dict:
    latencies = [row["total_s"] for row in turns]
    ttfts = [row["ttft_s"] for row in turns if row.get("ttft_s") is not None]
    tps = [row["decode_tokens_per_sec"] for row in turns if row.get("decode_tokens_per_sec")]
    return {
        "turns": len(turns),
        "latency_s": {
            "mean": round(statistics.fmean(latencies), 4) if latencies else None,
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "max": round(max(latencies), 4) if latencies else None,
        },
        "ttft_s": {
            "mean": round(statistics.fmean(ttfts), 4) if ttfts else None,
            "p50": percentile(ttfts, 50),
            "p95": percentile(ttfts, 95),
        },
        "decode_tokens_per_sec": {
            "mean": round(statistics.fmean(tps), 3) if tps else None,
            "p50": percentile(tps, 50),
            "p95": percentile(tps, 95),
        },
        "failures": sum(1 for row in turns if row.get("error")),
    }


def _run_session(url: str, prompts: list[str], n_predict: int, chat_format: str) -> list[dict]:
    history: list[tuple[str, str]] = []
    rows = []
    for index, user in enumerate(prompts):
        prompt, history = _render_prompt(history, user, chat_format)
        try:
            stop = ["<|im_end|>", "</s>", "<|im_start|>"] if chat_format == "checkpoint_chatml" else None
            row = _stream_completion(url, prompt, n_predict, cache_prompt=True, stop=stop)
            row["turn"] = index
            # Retain a response only while rendering the immediate next turn;
            # benchmark evidence intentionally stores no assistant text.
            history.append(("assistant", str(row.pop("content", ""))))
        except Exception as exc:
            row = {"turn": index, "error": type(exc).__name__, "total_s": None, "ttft_s": None}
        rows.append(row)
    return rows


def _powerinfer_child_env() -> dict[str, str]:
    """Make upstream's literal `python -m powerinfer` resolve to this venv.

    The native binaries are upstream code and invoke `python` by name while
    calculating a split. Running this script *with* a venv interpreter does
    not by itself change PATH for native child processes on Windows.
    """
    env = dict(os.environ)
    scripts = str(Path(sys.executable).resolve().parent)
    env["PATH"] = scripts + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = str(HERE) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _popen(cmd: list[str], log_path: Path, *, env: dict[str, str]) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        cmd,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    proc._log_handle = handle  # type: ignore[attr-defined]
    return proc


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
    handle = getattr(proc, "_log_handle", None)
    if handle:
        handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--main-exe", required=True)
    parser.add_argument("--server-exe", required=True)
    parser.add_argument("--gguf", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--vram-budget", type=float, default=12)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--context", type=int, default=2048)
    parser.add_argument("--turns", type=int, default=20)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--skip-gpu-preflight", action="store_true")
    args = parser.parse_args()

    from pipeline_lib import blocking_gpu_owners

    if not args.skip_gpu_preflight:
        owners = blocking_gpu_owners()
        if owners:
            raise SystemExit(f"GPU appears owned by {owners}; refuse acceptance-gate load")

    cfg = target_config(args.model_id)
    bundle = Path(args.bundle)
    validation = bundle / "validation"
    validation.mkdir(parents=True, exist_ok=True)
    run_stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    gguf = Path(args.gguf)
    # Packaging keeps activation files adjacent to the GGUF so the native
    # runtime can discover them. Older candidate layouts kept them at bundle
    # root; support that read-only legacy layout without copying or moving any
    # evidence.
    packaged_activation = gguf.parent / "activation"
    activation = packaged_activation if packaged_activation.is_dir() else bundle / "activation"
    predictor = bundle / "predictor"
    prompts_path = HERE / "prompts_20turn.json"
    prompts = json.loads(prompts_path.read_text(encoding="utf-8"))["turns"][: args.turns]
    url = f"http://{args.host}:{args.port}"

    hashes = {
        "gguf": {"path": str(gguf), "sha256": sha256_file(gguf), "bytes": gguf.stat().st_size},
        "predictor": sha256_tree(predictor, glob="*"),
        "activation": sha256_tree(activation, glob="activation_*.pt"),
        "prompts_file_sha256": sha256_file(prompts_path),
        "prompt_count": len(prompts),
    }

    smoke_cmd = [
        args.main_exe,
        "-m",
        str(gguf),
        "-n",
        "16",
        "-t",
        str(args.threads),
        "--vram-budget",
        str(args.vram_budget),
        "-c",
        str(args.context),
        "-p",
        "Once upon a time",
    ]
    before_smoke = {"gpu": gpu_snapshot(), "ram": host_ram_snapshot()}
    child_env = _powerinfer_child_env()
    smoke = subprocess.run(smoke_cmd, capture_output=True, text=True, timeout=1800, env=child_env)
    smoke_text = (smoke.stdout or "") + "\n" + (smoke.stderr or "")
    smoke_log_path = validation / f"main_smoke_bench_{run_stamp}.log"
    smoke_log_path.write_text(smoke_text, encoding="utf-8")
    split = parse_powerinfer_logs(smoke_text)
    after_smoke = {"gpu": gpu_snapshot(), "ram": host_ram_snapshot()}

    server = None
    bench = {"cold": None, "warm": None}
    server_error = None
    try:
        server_cmd = [
            args.server_exe,
            "-m",
            str(gguf),
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--vram-budget",
            str(args.vram_budget),
            "-t",
            str(args.threads),
            "-c",
            str(args.context),
            "-a",
            cfg["alias"],
        ]
        server_log_path = validation / f"server_{run_stamp}.log"
        server = _popen(server_cmd, server_log_path, env=child_env)
        _wait_http(url, args.host, args.port, timeout=180)
        cold_gpu = gpu_snapshot()
        cold_ram = host_ram_snapshot()
        bench["cold"] = {
            "started_at": utc_now(),
            "gpu": cold_gpu,
            "ram": cold_ram,
            "turns": _run_session(url, prompts, args.max_tokens, cfg["chat_format"]),
        }
        bench["cold"]["summary"] = _summarize(bench["cold"]["turns"])
        bench["warm"] = {
            "started_at": utc_now(),
            "gpu": gpu_snapshot(),
            "ram": host_ram_snapshot(),
            "turns": _run_session(url, prompts, args.max_tokens, cfg["chat_format"]),
        }
        bench["warm"]["summary"] = _summarize(bench["warm"]["turns"])
        bench["warm"]["gpu_end"] = gpu_snapshot()
        bench["warm"]["ram_end"] = host_ram_snapshot()
    except Exception as exc:
        server_error = f"{type(exc).__name__}: {exc}"
    finally:
        _stop(server)

    server_log = ""
    server_log_path = validation / f"server_{run_stamp}.log"
    if server_log_path.exists():
        server_log = server_log_path.read_text(encoding="utf-8", errors="replace")
    server_split = parse_powerinfer_logs(server_log)

    report = {
        "created_at": utc_now(),
        "model_id": args.model_id,
        "alias": cfg["alias"],
        "status": "candidate",
        "promoted_to_picker": False,
        "hashes": hashes,
        "smoke_main": {
            "returncode": smoke.returncode,
            "split": split,
            "gpu_before": before_smoke["gpu"],
            "gpu_after": after_smoke["gpu"],
            "ram_before": before_smoke["ram"],
            "ram_after": after_smoke["ram"],
            "log": str(smoke_log_path),
        },
        "server": {
            "url": url,
            "error": server_error,
            "split": server_split,
            "log": str(server_log_path),
        },
        "benchmark": {
            "turns_requested": args.turns,
            "max_tokens": args.max_tokens,
            "cold": {
                "summary": (bench["cold"] or {}).get("summary"),
                "gpu": (bench["cold"] or {}).get("gpu"),
                "ram": (bench["cold"] or {}).get("ram"),
                "turns": (bench["cold"] or {}).get("turns"),
            },
            "warm": {
                "summary": (bench["warm"] or {}).get("summary"),
                "gpu": (bench["warm"] or {}).get("gpu"),
                "ram": (bench["warm"] or {}).get("ram"),
                "gpu_end": (bench["warm"] or {}).get("gpu_end"),
                "ram_end": (bench["warm"] or {}).get("ram_end"),
                "turns": (bench["warm"] or {}).get("turns"),
            },
        },
        "acceptance_checklist": {
            "cuda_acceleration": split["cuda_acceleration"] or server_split["cuda_acceleration"],
            "ffn_split_working": split["ffn_split_working"] or server_split["ffn_split_working"],
            "activation_present": hashes["activation"]["count"] == cfg["num_hidden_layers"],
            "predictor_present": hashes["predictor"]["count"] >= cfg["num_hidden_layers"],
            "gguf_hashed": bool(hashes["gguf"]["sha256"]),
            "cold_20turn_recorded": bool((bench["cold"] or {}).get("summary")),
            "warm_20turn_recorded": bool((bench["warm"] or {}).get("summary")),
            "host_ram_recorded": host_ram_snapshot()["used_mb"] is not None,
            "vram_recorded": bool(gpu_snapshot().get("gpus")),
        },
    }
    # Do not keep assistant text. Turns already omit content.
    out = validation / f"acceptance_gate_{run_stamp}.json"
    write_json(out, report)
    print(json.dumps({"wrote": str(out), "checklist": report["acceptance_checklist"]}, indent=2))
    if smoke.returncode != 0 or server_error:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
