#!/usr/bin/env python3
"""Cloud DSPy compile for temporal-physics injection.

Temporary: BootstrapFewShot on grok-4.6 bakes few-shot demos into
models/dspy_compiled/temporal_physics_v1.json. That JSON is the local
runtime artifact; a later offline LM can load it without this compile step.

Requires: pip install dspy  and  XAI_API_KEY.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    import dspy
except ImportError:  # pragma: no cover
    dspy = None

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from evaluate_dspy_pipeline import (  # noqa: E402
    DEFAULT_JUDGE_MODEL,
    ValidateTemporalPhysics,
    configure_lm,
    evaluate_temporal_physics,
    gold_examples,
    load_trace_examples,
)

ARTIFACT_DIR = ROOT / "models" / "dspy_compiled"
ARTIFACT_PATH = ARTIFACT_DIR / "temporal_physics_v1.json"
EDGE_CASE = "A static tripod shot of a yellow hallway"

COMPILED_INSTRUCTIONS = """Given the fields `base_prompt`, `style`, produce the fields `reasoning`, `injected_prompt`.

For style=backrooms, expand the user request into one dense paragraph for an 8-second video diffusion model.

Required aesthetics when the camera is free — copy these exact tokens into injected_prompt, including the phrase handheld walking momentum: first-person camcorder tracking, heavy VHS artifacting, handheld walking momentum, continuous unbroken shot, realistic camera shake, 1990s home video aesthetic. Never omit handheld walking momentum on an unlocked camera.

Conflict rule: if the base prompt already specifies a locked or authored camera (tripod, static shot, static camera, security camera, CCTV, dolly, pan, tilt), suppress handheld walking momentum, first-person camcorder tracking, and realistic camera shake. Still keep heavy VHS artifacting, a continuous unbroken shot, and the 1990s home video aesthetic.

Do not duplicate phrases already present in the base prompt. Keep the original request as the first sentence."""

# Two dynamic + two locked/authored-camera demos. Live run_traces/ is empty;
# gold inject_temporal_physics strings are the ValidateTemporalPhysics-passing
# labels (same function the live orchestrator uses).
SYNTH_DEMOS = (
    {
        "kind": "dynamic",
        "base_prompt": "A yellow hallway with flickering fluorescent lights",
        "reasoning": (
            "The request is an open Backrooms hallway with no locked camera. "
            "Unlocked camera: injected_prompt MUST contain the exact phrase "
            "handheld walking momentum plus VHS, unbroken shot, shake, and 1990s."
        ),
    },
    {
        "kind": "dynamic",
        "base_prompt": (
            "Handheld walk down a Level 0 Backrooms corridor under flickering fluorescents"
        ),
        "reasoning": (
            "This is a walking first-person corridor. Keep handheld momentum and "
            "camcorder tracking. Add VHS, unbroken shot, shake, and 1990s texture "
            "without fighting the existing handheld language."
        ),
    },
    {
        "kind": "locked",
        "base_prompt": "A yellow hallway, static security camera footage",
        "reasoning": (
            "Static security camera is a locked operator. Suppress handheld walking "
            "momentum, first-person camcorder tracking, and camera shake. Keep VHS, "
            "unbroken shot, and 1990s home video."
        ),
    },
    {
        "kind": "locked",
        "base_prompt": "A static tripod shot of a yellow hallway",
        "reasoning": (
            "Tripod plus static shot forbids walking momentum and shake. Keep the "
            "locked framing and append only VHS artifacting, continuous unbroken "
            "shot, and 1990s home video aesthetic."
        ),
    },
)


if dspy is not None:
    class TemporalPhysicsInjector(dspy.Module):
        def __init__(self):
            super().__init__()
            self.prog = dspy.ChainOfThought("base_prompt, style -> injected_prompt")

        def forward(self, base_prompt, style):
            return self.prog(base_prompt=base_prompt, style=style)
else:  # pragma: no cover
    TemporalPhysicsInjector = None


def _fewshot_demos() -> list[dict]:
    """Four ValidateTemporalPhysics-passing demos from gold injects (no API)."""
    sys.path.insert(0, str(ROOT / "local_agent"))
    from temporal_physics import inject_temporal_physics

    demos = []
    for spec in SYNTH_DEMOS:
        injected = inject_temporal_physics(spec["base_prompt"], style="backrooms")
        example = type("Ex", (), {"base_prompt": spec["base_prompt"]})()
        pred = type("Pred", (), {"injected_prompt": injected})()
        if not evaluate_temporal_physics(example, pred):
            raise RuntimeError(
                f"synthesized demo failed evaluate_temporal_physics: {spec['base_prompt']!r}"
            )
        demos.append({
            "base_prompt": spec["base_prompt"],
            "style": "backrooms",
            "reasoning": spec["reasoning"],
            "injected_prompt": injected,
        })
    return demos


def synthesize_compiled_state() -> dict:
    """DSPy 2.6+ state-only JSON for TemporalPhysicsInjector (ChainOfThought).

    ``TemporalPhysicsInjector().load(path)`` reads named_parameters key
    ``prog.predict``: traces/train/demos + signature dump + lm.
    """
    return {
        "prog.predict": {
            "traces": [],
            "train": [],
            "demos": _fewshot_demos(),
            "signature": {
                "instructions": COMPILED_INSTRUCTIONS,
                "fields": [
                    {"prefix": "Base Prompt:", "description": "${base_prompt}"},
                    {"prefix": "Style:", "description": "${style}"},
                    {"prefix": "Reasoning:", "description": "${reasoning}"},
                    {"prefix": "Injected Prompt:", "description": "${injected_prompt}"},
                ],
            },
            "lm": None,
        },
        "metadata": {
            "dependency_versions": {
                "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                "dspy": "synthesized-offline",
                "cloudpickle": "synthesized-offline",
            },
            "source": "gold inject_temporal_physics; logs/run_traces empty",
            "n_demos": 4,
        },
    }


def write_synthesized_artifact(path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = synthesize_compiled_state()
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Wrote synthesized compiled state to {path}\n"
        "Load later with TemporalPhysicsInjector().load(path). The few-shot "
        "demonstrations and instructions are baked in; no cloud compile and no "
        "XAI_API_KEY are required to produce this file."
    )
    return path


def load_training_rows() -> list[dict]:
    """Gold Backrooms pairs, static-camera cases, and live run traces."""
    rows = []
    for row in gold_examples() + load_trace_examples():
        rows.append({
            "base_prompt": row["base_prompt"],
            "style": str(row.get("style") or "backrooms"),
            "injected_prompt": row["injected_prompt"],
            "case_id": row.get("case_id"),
        })
    return rows


def to_injector_examples(rows: list[dict]):
    if dspy is None:
        raise RuntimeError("dspy is not installed. Run: pip install dspy")
    examples = []
    for row in rows:
        examples.append(
            dspy.Example(
                base_prompt=row["base_prompt"],
                style=row.get("style") or "backrooms",
                injected_prompt=row["injected_prompt"],
            ).with_inputs("base_prompt", "style")
        )
    if not examples:
        raise RuntimeError("training set is empty")
    return examples


def compile_pipeline(*, max_bootstrapped_demos: int = 4, max_labeled_demos: int = 4):
    """Bootstrap few-shots for TemporalPhysicsInjector against evaluate_temporal_physics."""
    if dspy is None:
        raise RuntimeError("dspy is not installed. Run: pip install dspy")
    if ValidateTemporalPhysics is None:
        raise RuntimeError("ValidateTemporalPhysics is unavailable (dspy missing)")
    configure_lm(DEFAULT_JUDGE_MODEL)
    trainset = to_injector_examples(load_training_rows())
    student = TemporalPhysicsInjector()
    teleprompter = dspy.teleprompt.BootstrapFewShot(
        metric=evaluate_temporal_physics,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_labeled_demos,
    )
    return teleprompter.compile(student, trainset=trainset)


def save_compiled(program, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    program.save(str(path))
    print(
        f"Saved compiled temporal-physics module to {path}\n"
        "This JSON artifact bakes the optimized instructions and few-shot "
        "demonstrations. Load it later with TemporalPhysicsInjector().load(...) "
        "on a local LM — no further cloud compile, and no internet required "
        "once the local model is available."
    )
    return path


def verify_tripod_edge_case(program) -> str:
    """Run the static-tripod hallway case; fail if handheld physics leaks."""
    pred = program(base_prompt=EDGE_CASE, style="backrooms")
    text = str(getattr(pred, "injected_prompt", "") or "")
    lowered = text.lower()
    if "vhs" not in lowered and "1990s" not in lowered:
        raise SystemExit(
            f"compiled output dropped VHS/1990s aesthetic:\n{text}"
        )
    if "handheld walking momentum" in lowered or "realistic camera shake" in lowered:
        raise SystemExit(
            f"compiled output leaked handheld momentum or camera shake:\n{text}"
        )
    print("Edge-case OK: tripod shot kept VHS/1990s and suppressed handheld/shake.")
    print(text)
    return text


def main() -> int:
    if os.environ.get("XAI_API_KEY", "").strip() and dspy is not None:
        compiled = compile_pipeline()
        save_compiled(compiled)
        verify_tripod_edge_case(compiled)
        return 0
    write_synthesized_artifact()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
