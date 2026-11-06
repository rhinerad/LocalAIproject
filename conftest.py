"""Repository-wide pytest configuration.

The suite is written for the Windows workstation that runs the pipeline. On
any other machine (CI, a Linux clone) a test module can be unrunnable for
three environmental reasons, none of which is a product bug:

1. it imports an optional dependency that is not installed (dspy, torch, ...);
2. it imports one of the modules that live in the operator's ``work/`` folder
   (``image_render``, ``thermal_guard``, ...) which this checkout may lack;
3. it is Windows-only (``ctypes.windll``) or reads a vendored tree that is
   deliberately not committed (``local_agent/vendor_sideband``).

Rather than letting those show up as collection errors, this hook skips the
module and says why, so the remaining ~1,300 tests give a real signal.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
for p in (ROOT, ROOT / "local_agent"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

_OPTIONAL = {
    "dspy", "numpy", "PIL", "cryptography", "chromadb", "torch", "transformers",
    "cv2", "insightface", "onnxruntime", "huggingface_hub", "whisper",
    "faster_whisper", "ImageReward", "pydantic", "outlines", "psutil", "pynvml",
    "celery", "kombu", "redis", "RNS", "LXMF", "serial", "bleak", "winrt",
    "jnius", "kivy", "android", "safetensors", "datasets",
}
_WORK_ONLY = {
    "image_render", "thermal_guard", "batch_render_folder", "duration_ladder",
    "storyboard_from_story", "scene_reasoner", "harvest_good_audio_masters",
    "render_single_pass", "run_prompt_pack_production", "speech_density",
}
_WINDOWS_ONLY_TESTS = {"test_run_code.py"}
_NEEDS_VENDOR_SIDEBAND = {"test_sideband_tier_b.py", "test_saf_pyjnius_spike.py", "test_sealed_export.py"}

_cache: dict[str, bool] = {}


def _importable(mod: str) -> bool:
    if mod not in _cache:
        try:
            _cache[mod] = importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError):
            _cache[mod] = False
    return _cache[mod]


def _top_level_imports(path: pathlib.Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in tree.body:  # module level only; lazy imports inside functions are fine
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def _transitive_blockers(path: pathlib.Path, depth: int = 2) -> str | None:
    """Return a reason string if this module (or a local module it imports at
    top level, up to `depth` hops) needs something this machine lacks."""
    seen: set[pathlib.Path] = set()
    frontier = [(path, 0)]
    while frontier:
        cur, d = frontier.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for name in _top_level_imports(cur):
            if name in _WORK_ONLY and not _importable(name):
                return f"needs {name} from the operator's work/ folder"
            if name in _OPTIONAL and not _importable(name):
                return f"optional dependency {name} not installed"
            if d < depth:
                for base in (cur.parent, ROOT / "local_agent", ROOT):
                    cand = base / f"{name}.py"
                    if cand.is_file() and cand not in seen:
                        frontier.append((cand, d + 1))
    return None


def pytest_ignore_collect(collection_path, config):
    p = pathlib.Path(str(collection_path))
    if p.suffix != ".py" or not p.name.startswith("test_"):
        return None
    if os.name != "nt" and p.name in _WINDOWS_ONLY_TESTS:
        _note(config, p, "Windows-only")
        return True
    if p.name in _NEEDS_VENDOR_SIDEBAND and not (ROOT / "local_agent" / "vendor_sideband").is_dir():
        _note(config, p, "needs local_agent/vendor_sideband (not committed)")
        return True
    reason = _transitive_blockers(p)
    if reason:
        _note(config, p, reason)
        return True
    return None


def _note(config, path: pathlib.Path, reason: str) -> None:
    skipped = config.stash.setdefault(_SKIP_KEY, [])
    skipped.append((path.relative_to(ROOT).as_posix(), reason))


import pytest  # noqa: E402

_SKIP_KEY = pytest.StashKey[list]()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    skipped = config.stash.get(_SKIP_KEY, [])
    if not skipped:
        return
    terminalreporter.write_sep("-", f"{len(skipped)} test modules not collected on this machine")
    for path, reason in sorted(skipped):
        terminalreporter.write_line(f"  {path}: {reason}")
