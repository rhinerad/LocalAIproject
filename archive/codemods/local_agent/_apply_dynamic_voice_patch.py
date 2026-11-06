from pathlib import Path
import ast
import re
import textwrap

ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
ORCH = ROOT / "local_agent" / "dspy_orchestrator.py"
BATCH = ROOT / "batch_run_backrooms_gvd.py"
GV = ROOT / "generate_video.py"

HELPERS = r'''
# ---------------------------------------------------------------------------
# Dynamic audio cloning (C001 MiniMax native -> C002+ F5-TTS)
# Fail-open: missing wav / F5 / decode nodes => silent CreateVideo, never crash.
# ---------------------------------------------------------------------------

_QUOTED_DIALOGUE_RE = re.compile(r"[\'\"]([^\'\"]{2,240})[\'\"]")

C001_MASTER_VOICE_WAV = "C001_master_voice.wav"
C001_MASTER_VOICE_TXT = "C001_master_voice.txt"
MINIMAX_AUDIO_VAE_NAME = "minimax_h3_audio_vae_fp32.safetensors"
F5_TTS_CLASS = os.environ.get("GVD_F5_TTS_CLASS", "F5TTSAudio")
F5_LOAD_AUDIO_CLASS = os.environ.get("GVD_F5_LOAD_AUDIO_CLASS", "LoadAudio")


def extract_raw_dialogue(clip: dict | None) -> str:
    """Spoken line from the raw pack clip ONLY — never from DSPy output."""
    if not isinstance(clip, dict):
        return ""
    for key in ("dialogue", "spoken_line", "spoken_text", "line"):
        val = str(clip.get(key) or "").strip()
        if val:
            return val
    raw = str(
        clip.get("video_prompt")
        or clip.get("motion_prompt")
        or clip.get("video")
        or ""
    )
    m = _QUOTED_DIALOGUE_RE.search(raw)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"(?:says|saying|said)\s*[:\-]\s*(.+)$", raw, flags=re.IGNORECASE)
    if m2:
        return m2.group(1).strip().strip(" .")
    return ""


def _is_c001(clip_id: str) -> bool:
    cid = str(clip_id or "").strip().upper()
    if cid in {"C001", "1", "001"}:
        return True
    return cid.endswith("C001") or bool(re.search(r"(?:^|[_-])C?0*1$", cid))


def comfy_input_dir() -> Path:
    try:
        import mcp_client as _mcp
        return Path(_mcp.COMFYUI_PATH) / "input"
    except Exception:
        return Path(r"A:\Users\rhine\ComfyUI-Shared\input")


def c001_master_voice_paths() -> tuple[Path, Path]:
    base = comfy_input_dir()
    return base / C001_MASTER_VOICE_WAV, base / C001_MASTER_VOICE_TXT


def lock_c001_master_voice(
    c001_mp4: str | Path,
    *,
    raw_dialogue: str = "",
    ffmpeg_bin: str | None = None,
) -> Path:
    """Strip C001 MP4 audio -> ComfyUI/input/C001_master_voice.wav (+ .txt). Fail-open."""
    import shutil
    import subprocess

    mp4 = Path(c001_mp4)
    wav, txt = c001_master_voice_paths()
    wav.parent.mkdir(parents=True, exist_ok=True)
    txt.write_text((raw_dialogue or "").strip() + "\n", encoding="utf-8")
    ff = ffmpeg_bin or shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ff, "-y", "-i", str(mp4),
        "-vn", "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
        str(wav),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"  C001 master voice locked -> {wav}")
    except Exception as exc:
        print(f"  C001 master-voice extract failed ({exc}); C002+ may be silent")
    return wav


def _find_node_by_class(graph: dict, class_type: str) -> str | None:
    for nid, node in graph.items():
        if isinstance(node, dict) and str(node.get("class_type") or "") == class_type:
            return str(nid)
    return None


def strip_f5_voice_nodes(graph: dict) -> dict:
    """Remove F5 helper nodes and clear mux audio (silent fallback)."""
    if not isinstance(graph, dict):
        return graph
    for drop in ("90", "91"):
        graph.pop(drop, None)
    for class_type in ("CreateVideo", "VHS_VideoCombine"):
        nid = _find_node_by_class(graph, class_type)
        if nid and isinstance(graph.get(nid), dict):
            inputs = dict(graph[nid].get("inputs") or {})
            inputs.pop("audio", None)
            graph[nid] = {**graph[nid], "inputs": inputs}
    return graph


def apply_dynamic_voice_routing(
    graph: dict,
    *,
    clip_id: str,
    raw_dialogue: str = "",
    enable_f5: bool = True,
) -> dict:
    """C001: MiniMax native audio -> CreateVideo.
    C002+: F5-TTS(C001_master_voice.wav, pack dialogue) -> CreateVideo.
    Fail-open => silent CreateVideo.
    """
    if not isinstance(graph, dict):
        return graph

    g = graph
    create_id = _find_node_by_class(g, "CreateVideo")
    combine_id = _find_node_by_class(g, "VHS_VideoCombine")
    mux_id = create_id or combine_id
    if mux_id is None:
        print("  voice routing: no CreateVideo/VHS_VideoCombine; leaving silent")
        return g

    for drop in ("42", "43", "44", "90", "91"):
        g.pop(drop, None)

    inputs = dict(g[mux_id].get("inputs") or {})
    inputs.pop("audio", None)

    if _is_c001(clip_id):
        sampler_id = _find_node_by_class(g, "SamplerCustomAdvanced") or "37"
        g["42"] = {
            "class_type": "VAELoader",
            "inputs": {"vae_name": MINIMAX_AUDIO_VAE_NAME},
        }
        g["43"] = {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": [sampler_id, 0], "vae": ["42", 0]},
        }
        g["44"] = {
            "class_type": "SanitizeGeneratedAudio",
            "inputs": {"audio": ["43", 0]},
        }
        inputs["audio"] = ["44", 0]
        g[mux_id] = {**g[mux_id], "inputs": inputs}
        print(f"  voice routing [{clip_id}]: MiniMax native audio -> {mux_id}")
        return g

    if not enable_f5:
        g[mux_id] = {**g[mux_id], "inputs": inputs}
        print(f"  voice routing [{clip_id}]: F5 disabled; silent")
        return g

    dialogue = (raw_dialogue or "").strip()
    if not dialogue:
        g[mux_id] = {**g[mux_id], "inputs": inputs}
        print(f"  voice routing [{clip_id}]: empty pack dialogue; silent")
        return g

    wav, txt = c001_master_voice_paths()
    if not wav.is_file():
        g[mux_id] = {**g[mux_id], "inputs": inputs}
        print(f"  voice routing [{clip_id}]: missing {wav.name}; silent")
        return g

    ref_text = txt.read_text(encoding="utf-8").strip() if txt.is_file() else ""
    if not ref_text:
        ref_text = dialogue

    g["90"] = {
        "class_type": F5_LOAD_AUDIO_CLASS,
        "inputs": {"audio": C001_MASTER_VOICE_WAV},
    }
    g["91"] = {
        "class_type": F5_TTS_CLASS,
        "inputs": {
            "ref_audio": ["90", 0],
            "audio": ["90", 0],
            "sample": ["90", 0],
            "ref_text": ref_text,
            "gen_text": dialogue,
            "text": dialogue,
            "seed": 42,
        },
    }
    inputs["audio"] = ["91", 0]
    g[mux_id] = {**g[mux_id], "inputs": inputs}
    print(f"  voice routing [{clip_id}]: F5-TTS gen_text={dialogue[:60]!r} -> {mux_id}")
    return g
'''

def main() -> None:
    orch = ORCH.read_text(encoding="utf-8")

    # Ensure `os` and `re` imported
    if "import os" not in orch.split("def ")[0]:
        orch = orch.replace("import json\n", "import json\nimport os\n", 1)
    if re.search(r"^import re\b", orch, re.M) is None and re.search(r"^from re ", orch, re.M) is None:
        orch = orch.replace("import os\n", "import os\nimport re\n", 1)

    # Remove prior helper block if re-applying
    orch = re.sub(
        r"\n# ---------------------------------------------------------------------------\n# Dynamic audio cloning[\s\S]*?(?=\ndef build_minimax_graph\()",
        "\n",
        orch,
        count=1,
    )

    idx = orch.find("def build_minimax_graph(")
    if idx < 0:
        raise SystemExit("build_minimax_graph not found")
    orch = orch[:idx] + HELPERS + "\n\n" + orch[idx:]

    old_sig = '''def build_minimax_graph(
    start_prompt: str,
    video_prompt: str,
    hparams: dict[str, float],
    *,
    negative: str = "",
    prefix: str = "dspy_opt/gvd_minimax",
    stills_only: bool = False,
) -> dict:'''
    new_sig = '''def build_minimax_graph(
    start_prompt: str,
    video_prompt: str,
    hparams: dict[str, float],
    *,
    negative: str = "",
    prefix: str = "dspy_opt/gvd_minimax",
    stills_only: bool = False,
    clip_id: str = "",
    raw_dialogue: str = "",
    enable_f5_voice: bool = True,
) -> dict:'''
    if old_sig not in orch:
        raise SystemExit("signature mismatch")
    orch = orch.replace(old_sig, new_sig, 1)

    # Hook before return inside build_minimax_graph
    build_start = orch.find("def build_minimax_graph(")
    build_end = orch.find("\ndef build_wan_graph(", build_start)
    if build_end < 0:
        build_end = orch.find("\ndef _director_start_prompt(", build_start)
    block = orch[build_start:build_end]
    if "apply_dynamic_voice_routing(" not in block:
        needle = "    return graph\n"
        insert = '''    if not stills_only:
        graph = apply_dynamic_voice_routing(
            graph,
            clip_id=str(clip_id or ""),
            raw_dialogue=str(raw_dialogue or ""),
            enable_f5=bool(enable_f5_voice),
        )
    return graph
'''
        # replace last return graph in this function only
        pos = block.rfind(needle)
        if pos < 0:
            raise SystemExit("return graph not found in build_minimax_graph")
        block = block[:pos] + insert + block[pos + len(needle):]
        orch = orch[:build_start] + block + orch[build_end:]

    old_call = '''    graph = build_minimax_graph(
        start_prompt,
        video_prompt,
        hparams,
        negative=negative,
        prefix=prefix,
        stills_only=bool(stills_only),
    )'''
    new_call = '''    raw_dialogue = str(
        _field(example, "raw_dialogue")
        or _field(example, "pack_dialogue")
        or _field(pred, "raw_dialogue")
        or ""
    ).strip()
    graph = build_minimax_graph(
        start_prompt,
        video_prompt,
        hparams,
        negative=negative,
        prefix=prefix,
        stills_only=bool(stills_only),
        clip_id=str(clip_id or ""),
        raw_dialogue=raw_dialogue,
        enable_f5_voice=os.environ.get("GVD_F5_TTS", "1") != "0",
    )'''
    if old_call not in orch:
        raise SystemExit("build_minimax_graph call site not found")
    orch = orch.replace(old_call, new_call, 1)

    old_submit = "        queued = orch.submit_prompt(_comfy_prompt_graph(graph))"
    new_submit = '''        try:
            queued = orch.submit_prompt(_comfy_prompt_graph(graph))
        except Exception as _sub_exc:
            _msg = str(_sub_exc).lower()
            if any(
                k in _msg
                for k in (
                    "f5",
                    "tts",
                    "loadaudio",
                    "vaedecodeaudio",
                    "sanitizegeneratedaudio",
                    "class_type",
                    "node",
                )
            ):
                print(f"  voice submit failed ({_sub_exc}); retrying silent")
                graph = strip_f5_voice_nodes(graph)
                for _drop in ("42", "43", "44"):
                    graph.pop(_drop, None)
                for _ct in ("CreateVideo", "VHS_VideoCombine"):
                    _cid = _find_node_by_class(graph, _ct)
                    if _cid and isinstance(graph.get(_cid), dict):
                        _in = dict(graph[_cid].get("inputs") or {})
                        _in.pop("audio", None)
                        graph[_cid] = {**graph[_cid], "inputs": _in}
                queued = orch.submit_prompt(_comfy_prompt_graph(graph))
            else:
                raise'''
    if old_submit not in orch:
        raise SystemExit("submit_prompt site not found")
    orch = orch.replace(old_submit, new_submit, 1)

    ORCH.write_text(orch, encoding="utf-8")
    ast.parse(orch)
    print("ORCH AST OK")

    # ---- generate_video.py: thread raw_dialogue ----
    gv = GV.read_text(encoding="utf-8")
    if "raw_dialogue" not in gv:
        # patch def submit_comfy signature
        sig_old = "def submit_comfy(pred, hparams: dict, *, clip_id: str = \"cli\", category: str = \"\") -> Path:"
        # try variants
        m = re.search(r"def submit_comfy\([^\)]*\)\s*->\s*Path:", gv)
        if not m:
            raise SystemExit("submit_comfy not found")
        print("submit_comfy sig:", m.group(0))
        old_sig = m.group(0)
        if "raw_dialogue" not in old_sig:
            new_sig = old_sig.replace(
                ") -> Path:",
                ", raw_dialogue: str = \"\") -> Path:",
            )
            # if already has kwargs ending differently
            if new_sig == old_sig:
                new_sig = old_sig.replace("category: str = \"\"", "category: str = \"\", raw_dialogue: str = \"\"")
            gv = gv.replace(old_sig, new_sig, 1)

        # example SimpleNamespace — add raw_dialogue=
        if "example = SimpleNamespace(" in gv and "raw_dialogue=" not in gv:
            gv = gv.replace(
                "example = SimpleNamespace(",
                "example = SimpleNamespace(\n        raw_dialogue=str(raw_dialogue or \"\"),\n        pack_dialogue=str(raw_dialogue or \"\"),",
                1,
            )
        GV.write_text(gv, encoding="utf-8")
        ast.parse(gv)
        print("GV AST OK")
    else:
        print("GV already has raw_dialogue")
        ast.parse(gv)

    # ---- batch runner hook ----
    batch = BATCH.read_text(encoding="utf-8")
    if "lock_c001_master_voice" not in batch:
        # ensure import path
        if "import dspy_orchestrator" not in batch and "import dspy_orchestrator as" not in batch:
            # add local import near other imports
            batch = batch.replace(
                "import generate_video as gv\n",
                "import generate_video as gv\n",
                1,
            )

        # After successful submit_comfy / video_path assignment, inject extraction + pass dialogue
        # Find submit_comfy call
        if "gv.submit_comfy(" not in batch:
            raise SystemExit("batch submit_comfy call not found")

        # Replace the submit block to pass raw_dialogue and lock C001 voice
        # Locate region around video_path = gv.submit_comfy
        pattern = re.compile(
            r"video_path = gv\.submit_comfy\(\s*pred,\s*hparams,\s*clip_id=f\"br_\{cid\.lower\(\)\}\",\s*category=DEFAULT_CATEGORY,\s*stills_only=bool\(args\.stills_only\),\s*\)",
            re.S,
        )
        m = pattern.search(batch)
        if not m:
            # looser
            m = re.search(r"video_path = gv\.submit_comfy\([\s\S]*?\)", batch)
            if not m:
                raise SystemExit("could not match submit_comfy call")
            print("loose match:\n", m.group(0)[:400])

        replacement = '''# Pack dialogue ONLY (never DSPy paraphrase) for F5 / C001 voice lock
            import dspy_orchestrator as _orch_voice
            raw_dialogue = _orch_voice.extract_raw_dialogue(clip)
            if raw_dialogue:
                print(f"  pack dialogue: {raw_dialogue[:120]!r}")

            video_path = gv.submit_comfy(
                pred,
                hparams,
                clip_id=f"br_{cid.lower()}",
                category=DEFAULT_CATEGORY,
                stills_only=bool(args.stills_only),
                raw_dialogue=raw_dialogue,
            )
            # C001: lock MiniMax native audio as the clone reference for C002+
            if (not args.stills_only) and _orch_voice._is_c001(cid):
                try:
                    _orch_voice.lock_c001_master_voice(
                        Path(video_path),
                        raw_dialogue=raw_dialogue,
                    )
                except Exception as _voice_exc:
                    print(f"  C001 voice-lock hook error (fail-open): {_voice_exc}")'''

        batch = batch[:m.start()] + replacement + batch[m.end():]
        BATCH.write_text(batch, encoding="utf-8")
        ast.parse(batch)
        print("BATCH AST OK")
    else:
        print("BATCH already patched")
        ast.parse(batch)

    # quick unit check extract + routing without comfy
    import sys
    sys.path.insert(0, str(ROOT / "local_agent"))
    import importlib
    import dspy_orchestrator as orch
    importlib.reload(orch)

    assert orch.extract_raw_dialogue({"video_prompt": 'He says: "Hello there friend."'}) == "Hello there friend."
    g = {
        "37": {"class_type": "SamplerCustomAdvanced", "inputs": {}},
        "39": {"class_type": "CreateVideo", "inputs": {"images": ["38", 0], "fps": 24}},
        "25": {"class_type": "SaveVideo", "inputs": {"video": ["39", 0]}},
    }
    g1 = orch.apply_dynamic_voice_routing(dict(g), clip_id="C001", raw_dialogue="Hi")
    assert g1["39"]["inputs"]["audio"] == ["44", 0], g1["39"]
    g2 = orch.apply_dynamic_voice_routing(dict(g), clip_id="C002", raw_dialogue="Hi")
    assert "audio" not in g2["39"]["inputs"], "missing wav => silent"
    print("UNIT CHECKS OK")

if __name__ == "__main__":
    main()