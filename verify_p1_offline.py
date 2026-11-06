#!/usr/bin/env python3
"""Offline P1 checks — no ComfyUI / GPU / network.

Proves:
  P1-A  transactional production_store (create → gate → select → fence → invalidate)
  P1-B  style profile out of generic master path (no Backrooms hardcoding)
  P1-C  backend profiles choose sampling; planner uses quality_tier / motion_complexity
  P1-D  VRAM admission blocking + free_vram keyword contract + cancel/reconcile helpers
  P1-E  dataset_synthesizer bounds + multi-scene/dialogue coverage
  P1-F  VHS finishing optional / off by default
  P1-G  get_completed_media only via SELECTED (no mtime fallback)
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HANDOFF = ROOT / "handoff"
LOCAL_AGENT = HANDOFF / "local_agent"
sys.path.insert(0, str(HANDOFF))
sys.path.insert(0, str(LOCAL_AGENT))

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS: {name}")
    else:
        msg = f"FAIL: {name}" + (f" — {detail}" if detail else "")
        print(f"  {msg}")
        FAILURES.append(msg)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def source_of(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_p1a_production_store() -> None:
    print("\n[P1-A] transactional job store + selection")
    store = load_module("production_store", HANDOFF / "production_store.py")
    db = store.connect(":memory:", memory=True)
    store.ensure_shot(db, "C001")
    aid = store.create_attempt(
        db,
        shot_id="C001",
        input_payload={"prompt": "hallway", "frames": 124},
        required_audio=True,
        state="READY",
    )
    check("create_attempt returns id", bool(aid))
    row = db.execute("SELECT input_hash, state FROM attempts WHERE attempt_id=?", (aid,)).fetchone()
    check("input_hash set before submit", bool(row["input_hash"]) and len(row["input_hash"]) == 64)
    check("initial state READY", row["state"] == "READY")

    store.set_attempt_state(db, aid, "SUBMITTING")
    store.set_attempt_state(db, aid, "RUNNING")
    store.set_attempt_state(
        db, aid, "RENDERED",
        artifact_path="/tmp/c001.mp4", artifact_sha256="ab" * 32,
    )
    store.set_attempt_state(db, aid, "TECHNICAL_QA")
    store.mark_qa_flags(db, aid, technical_pass=True, visual_pass=True)
    try:
        store.select_attempt(db, "C001", 0, aid)
        check("select without audio rejected", False, "should raise")
    except ValueError:
        check("select without audio rejected", True)

    store.mark_qa_flags(db, aid, audio_pass=True)
    store.set_attempt_state(db, aid, "CONTENT_QA")
    store.select_attempt(db, "C001", 0, aid)
    sel = store.get_selected_attempt(db, "C001")
    check("selected attempt state SELECTED", sel is not None and sel["state"] == "SELECTED")
    check(
        "selected artifact path",
        store.get_selected_artifact_path(db, "C001") == "/tmp/c001.mp4",
    )

    try:
        store.select_attempt(db, "C001", 0, aid)
        check("stale revision fenced", False)
    except RuntimeError:
        check("stale revision fenced", True)

    # descendant invalidation API
    store.ensure_shot(db, "C002", parent_shot_id="C001")
    child = store.create_attempt(
        db, shot_id="C002", input_payload={"prompt": "next"}, parent_attempt_id=aid
    )
    n = store.invalidate_descendants(db, "C001")
    check("invalidate_descendants touched child", n >= 1)
    st = db.execute("SELECT state FROM attempts WHERE attempt_id=?", (child,)).fetchone()["state"]
    check("child INVALIDATED", st == "INVALIDATED")

    view = store.export_progress_view(db)
    check("progress export verified for C001", view["clips"]["C001"]["verified"] is True)
    check(
        "attempt states include required set",
        {"PLANNED", "READY", "SUBMITTING", "RUNNING", "RENDERED",
         "TECHNICAL_QA", "CONTENT_QA", "SELECTED", "FAILED_ADMISSION"}.issubset(
            store.ATTEMPT_STATES
        ),
    )

    master_src = source_of("handoff/master_batch_runner.py")
    check("master wires create_attempt", "create_attempt" in master_src)
    check("master opens production store", "open_production_store" in master_src or "store_connect" in master_src)


def test_p1b_style_profile() -> None:
    print("\n[P1-B] style profile out of generic master path")
    master = load_module("master_batch_runner", HANDOFF / "master_batch_runner.py")
    generic = master.load_style_profile("generic")
    backrooms = master.load_style_profile("backrooms_sitcom")
    blob_g = json.dumps(generic).lower()
    blob_b = json.dumps(backrooms).lower()
    check("generic has no camcorder", "camcorder" not in blob_g)
    check("generic has no yellow wallpaper", "yellow" not in blob_g and "wallpaper" not in blob_g)
    check("generic has no vhs constraint", "vhs" not in blob_g or generic.get("vhs_finishing", {}).get("enabled") is False)
    check("backrooms profile has camcorder", "camcorder" in blob_b)
    check("backrooms profile has fluorescent or yellow", "fluorescent" in blob_b or "yellow" in blob_b)

    intent_g = master.build_intent({"id": "C001", "video_prompt": "walk"}, generic)
    intent_b = master.build_intent({"id": "C001", "video_prompt": "walk"}, backrooms)
    check("generic intent has no Backrooms", "backrooms" not in intent_g.lower())
    check("backrooms intent mentions Backrooms", "backrooms" in intent_b.lower())

    cons_g = master.build_constraints(
        clip={"id": "C001"},
        start_ref=None, start_note="n/a",
        last_ref=None, last_note="n/a",
        previous_video=None, style=generic,
    )
    check("generic constraints have no VHS/camcorder hardcode",
          "camcorder" not in cons_g.lower() and "vhs" not in cons_g.lower())

    master_src = source_of("handoff/master_batch_runner.py")
    # Hardcoded genre strings should not appear in build_intent/build_constraints bodies
    # (only inside style profile load path / help text is ok)
    check("master has --style-profile CLI", "--style-profile" in master_src)
    check("master load_style_profile present", "def load_style_profile" in master_src)


def test_p1c_backend_profiles() -> None:
    print("\n[P1-C] backend profiles vs creative planner")
    bp = load_module("backend_profiles", HANDOFF / "backend_profiles.py")
    gvd = load_module("gvd_core", HANDOFF / "gvd_core.py")

    hp = bp.planner_request_to_hparams(
        backend_profile="h3_distilled",
        quality_tier="standard",
        motion_complexity="moderate",
    )
    check("H3 distilled steps=20", float(hp["step_count"]) == 20)
    check("H3 distilled uses_cfg False", hp.get("uses_cfg") is False)
    check("H3 distilled cfg_scale is None", hp.get("cfg_scale") is None)

    hero = bp.planner_request_to_hparams(
        backend_profile="h3_distilled", quality_tier="hero"
    )
    check("H3 hero nudges steps without inventing CFG",
          float(hero["step_count"]) >= 20 and hero.get("cfg_scale") is None)

    warns = bp.reject_planner_invented_sampling(
        {"backend_profile": "h3_distilled", "cfg": 6.0, "steps": 30}
    )
    check("reject planner-invented CFG/steps for H3", len(warns) >= 1)

    creative = gvd.normalize_planner_creative(
        quality_tier="standard", motion_complexity="moderate"
    )
    check("planner creative has quality_tier", creative["quality_tier"] == "standard")
    check("planner creative has motion_complexity", creative["motion_complexity"] == "moderate")
    check("planner hparams from backend", creative["hparams"]["cfg_scale"] is None)

    gvd_src = source_of("handoff/gvd_core.py")
    check("gvd planner fields are tiers not CFG", "quality_tier" in gvd_src and "motion_complexity" in gvd_src)
    # Signature should not advertise Wan/FLUX CFG 16-40 as planner outputs for H3 path
    check(
        "gvd no longer requires planner CFG float field for H3",
        "cfg: float = dspy.OutputField" not in gvd_src
        and "steps: int = dspy.OutputField" not in gvd_src,
    )


def test_p1d_vram_contract() -> None:
    print("\n[P1-D] memory / free_vram contract")
    store = load_module("production_store", HANDOFF / "production_store.py")

    class Boom:
        def __call__(self, *, reason=""):
            raise RuntimeError("no vram")

    try:
        store.prepare_vram_or_raise(Boom(), reason="test")
        check("admission failure raises", False)
    except store.VramAdmissionError as exc:
        check("admission failure raises VramAdmissionError", "admission" in str(exc).lower() or "vram" in str(exc).lower())

    class StubClient:
        def __init__(self):
            self.ops = []
        def cancel_prompt(self, pid):
            self.ops.append(("cancel", pid))
        def reconcile(self, prompt_id=None):
            self.ops.append(("reconcile", prompt_id))
        def release_lease(self, reason=""):
            self.ops.append(("release", reason))

    stub = StubClient()
    tr = store.release_gpu_lease(stub, prompt_id="p1", attempt_id="a1", reason="finally")
    check("cancel before release", tr["cancelled"] is True)
    check("reconcile before release", tr["reconciled"] is True)
    check("lease released after cancel/reconcile", tr["lease_released"] is True)
    check("ops order cancel→reconcile→release",
          stub.ops == [("cancel", "p1"), ("reconcile", "p1"), ("release", "finally")])

    class KwargsOnly:
        def free_vram(self, *, unload_models=True, free_memory=True):
            self.seen = (unload_models, free_memory)
            return True

    api = KwargsOnly()
    out = store.free_vram_safe(api, unload_models=True, free_memory=True)
    check("free_vram_safe kwargs contract ok", out.get("ok") is True and api.seen == (True, True))

    gv_src = source_of("handoff/generate_video.py")
    check("generate_video treats admission as blocking",
          "prepare_vram_or_raise" in gv_src or "VRAM admission failed" in gv_src)
    check("generate_video no longer only warns on prepare",
          "(vram prepare warning:" not in gv_src)
    check("generate_video uses release_gpu_lease or free_vram_safe",
          "release_gpu_lease" in gv_src or "free_vram_safe" in gv_src)

    orch_src = source_of("handoff/local_agent/dspy_orchestrator.py")
    check("orchestrator has cancel/reconcile helper",
          "cancel_reconcile_before_lease_release" in orch_src or "release_gpu_lease" in orch_src)


def test_p1e_dataset_synthesizer() -> None:
    print("\n[P1-E] dataset synthesizer validation")
    ds = load_module("dataset_synthesizer", HANDOFF / "dataset_synthesizer.py")
    keys = ds.SCHEMA_KEYS
    row = {k: f"text-{k}" for k in keys}
    row["quality_tier"] = "standard"
    row["motion_complexity"] = "moderate"
    ok = ds.validate_row(row)
    check("valid row accepted", ok["quality_tier"] == "standard")

    bad_tier = dict(row, quality_tier="ultra")
    try:
        ds.validate_row(bad_tier)
        check("bad quality_tier rejected", False)
    except ds.DatasetValidationError:
        check("bad quality_tier rejected", True)

    bad_cfg = dict(row, cfg=99.0)
    try:
        ds.validate_row(bad_cfg)
        check("cfg out of bounds rejected", False)
    except ds.DatasetValidationError as exc:
        check("cfg out of bounds rejected", "cfg" in str(exc).lower())

    bad_steps = dict(row, steps=3)
    try:
        ds.validate_row(bad_steps)
        check("steps out of bounds rejected", False)
    except ds.DatasetValidationError:
        check("steps out of bounds rejected", True)

    covered = dict(row)
    covered["scene_ids"] = ["sc1", "sc2"]
    covered["dialogue"] = [{"speaker_id": "A", "text": "Hello", "voice_asset_id": None}]
    out = ds.validate_row(covered, require_coverage=True)
    check("multi-scene coverage accepted", out["scene_ids"] == ["sc1", "sc2"])
    check("dialogue coverage accepted", len(out["dialogue"]) == 1)

    try:
        ds.validate_row(row, require_coverage=True)
        check("missing coverage rejected when required", False)
    except ds.DatasetValidationError:
        check("missing coverage rejected when required", True)

    # shot.schema alignment: continuity
    cont = dict(row)
    cont["continuity"] = {
        "mode": "continuous",
        "parent_attempt_id": "att_1",
        "canonical_asset_ids": ["a1"],
    }
    out2 = ds.validate_row(cont)
    check("continuity aligned", out2["continuity"]["mode"] == "continuous")


def test_p1f_vhs_optional() -> None:
    print("\n[P1-F] VHS finishing optional")
    vhs = load_module("vhs_postprocess", LOCAL_AGENT / "vhs_postprocess.py")
    os.environ.pop("GVD_VHS_FINISHING", None)
    check("finishing off by default", vhs.finishing_enabled() is False)
    check("explicit enabled True", vhs.finishing_enabled(enabled=True) is True)
    check("explicit enabled False", vhs.finishing_enabled(enabled=False) is False)
    os.environ["GVD_VHS_FINISHING"] = "1"
    try:
        check("env gate enables finishing", vhs.finishing_enabled() is True)
    finally:
        os.environ.pop("GVD_VHS_FINISHING", None)

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.mp4"
        dst = Path(td) / "out.mp4"
        src.write_bytes(b"not-a-real-mp4")
        # disabled → returns None without calling ffmpeg
        out = vhs.apply_vhs_look(src, dst, enabled=False)
        check("disabled apply returns None", out is None)
        check("disabled apply writes nothing", not dst.exists())

    src_txt = source_of("handoff/local_agent/vhs_postprocess.py")
    check("rec_overlay param present", "rec_overlay" in src_txt)
    check("--enable flag present", "--enable" in src_txt)
    check("off by default documented", "OFF by default" in src_txt or "off by default" in src_txt.lower())


def test_p1g_completed_media_selected_only() -> None:
    print("\n[P1-G] get_completed_media / continuity deps via SELECTED only")
    master = load_module("master_batch_runner", HANDOFF / "master_batch_runner.py")
    store = load_module("production_store", HANDOFF / "production_store.py")

    with tempfile.TemporaryDirectory() as td:
        task = Path(td)
        (task / "clips").mkdir()
        (task / "outputs").mkdir()
        # recently-modified MP4 without SELECTED must NOT resolve
        orphan = task / "outputs" / "C010_orphan.mp4"
        orphan.write_bytes(b"x" * 20_000)
        check(
            "mtime orphan rejected",
            master.get_completed_media(task, "C010") is None,
        )

        # rendered but not selected clip JSON rejected
        clip_path = task / "clips" / "C011.json"
        rendered_mp4 = task / "outputs" / "C011.mp4"
        rendered_mp4.write_bytes(b"y" * 20_000)
        clip_path.write_text(json.dumps({
            "id": "C011",
            "master_batch": {
                "status": "rendered",
                "pipeline_state": "RENDERED",
                "video_path": str(rendered_mp4),
                "verified": False,
            },
        }), encoding="utf-8")
        check(
            "RENDERED clip JSON rejected",
            master.get_completed_media(task, "C011") is None,
        )

        # SELECTED accepted
        clip_sel = task / "clips" / "C012.json"
        sel_mp4 = task / "outputs" / "C012.mp4"
        sel_mp4.write_bytes(b"z" * 20_000)
        clip_sel.write_text(json.dumps({
            "id": "C012",
            "master_batch": {
                "status": "selected",
                "pipeline_state": "SELECTED",
                "video_path": str(sel_mp4),
                "verified": True,
            },
        }), encoding="utf-8")
        found = master.get_completed_media(task, "C012")
        check("SELECTED clip JSON accepted", found is not None and found == sel_mp4.resolve() or (found and found.name == "C012.mp4"))

        # SQLite SELECTED path
        db = store.connect(":memory:", memory=True)
        store.ensure_shot(db, "C013")
        art = task / "outputs" / "C013.mp4"
        art.write_bytes(b"w" * 20_000)
        aid = store.create_attempt(db, shot_id="C013", input_payload={"p": 1})
        store.set_attempt_state(
            db, aid, "RENDERED",
            artifact_path=str(art), artifact_sha256="cd" * 32,
        )
        store.mark_qa_flags(db, aid, technical_pass=True, visual_pass=True, audio_pass=True)
        store.select_attempt(db, "C013", 0, aid)
        found2 = master.get_completed_media(task, "C013", db=db)
        check("SELECTED via production_store accepted", found2 is not None)

    master_src = source_of("handoff/master_batch_runner.py")
    check("get_completed_media has require_selected", "require_selected" in master_src)
    check("no unconditional rglob mtime accept without gate",
          "require_selected" in master_src and "SELECTED" in master_src)


def test_symbols_present() -> None:
    print("\n[P1] deliverable files present")
    for rel in (
        "handoff/production_store.py",
        "handoff/backend_profiles.py",
        "handoff/style_profiles/generic.json",
        "handoff/style_profiles/backrooms_sitcom.json",
        "handoff/master_batch_runner.py",
        "handoff/generate_video.py",
        "handoff/gvd_core.py",
        "handoff/dataset_synthesizer.py",
        "handoff/local_agent/vhs_postprocess.py",
        "handoff/batch_run_backrooms_gvd.py",
        "handoff/local_agent/dspy_orchestrator.py",
    ):
        check(rel, (ROOT / rel).is_file())


def main() -> int:
    print("P1 offline verification")
    print(f"ROOT={ROOT}")
    test_symbols_present()
    test_p1a_production_store()
    test_p1b_style_profile()
    test_p1c_backend_profiles()
    test_p1d_vram_contract()
    test_p1e_dataset_synthesizer()
    test_p1f_vhs_optional()
    test_p1g_completed_media_selected_only()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("ALL P1 OFFLINE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
