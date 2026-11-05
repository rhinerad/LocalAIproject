from pathlib import Path
import re
import py_compile

path = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\work\run_prompt_pack_production.py")
text = path.read_text(encoding="utf-8")

old = '''    v5_first_quality_failure = policy_failure_count(
        attempt_root, "c001-smile-facedetailer-ipadapter-v5",
        "face-crop-full-dependencies-repaired-v3",
    ) >= 1
    recovered["qa_prompt"] = str(job.get("qa_prompt") or job.get("prompt") or "")
'''

new = '''    v5_first_quality_failure = policy_failure_count(
        attempt_root, "c001-smile-facedetailer-ipadapter-v5",
        "face-crop-full-dependencies-repaired-v3",
    ) >= 1
    v5_strong_smile_failure = policy_failure_count(
        attempt_root, "c001-smile-facedetailer-ipadapter-v5",
        "face-crop-strong-smile-guidance-v4",
    ) >= 1
    recovered["qa_prompt"] = str(job.get("qa_prompt") or job.get("prompt") or "")
'''

if old not in text:
    raise SystemExit("v5_first_quality_failure block not found")
text = text.replace(old, new, 1)

old2 = '''    if v4_failed:
        if v5_first_quality_failure:
            recovered["prompt"] = (
                "portrait detail of the same adult man, (warm friendly practiced "
                "sitcom smile:1.5), (relaxed naturally upturned mouth corners:1.4), "
                "subtly lifted cheeks, pleasant cheerful eyes, short dark-brown "
                "hair, natural brown beard and mustache, realistic skin, exact "
                "same identity"
            )
            recovered["negative"] = (
                "frown, scowl, stern expression, serious expression, angry, grimace, "
                "downturned mouth, pursed lips, blue object, object over mouth, mask, "
                "open mouth, oversized teeth, deformed teeth, duplicate face, face "
                "seam, different person, different beard, different hair"
            )
            recovered["denoise"] = 0.42
        else:
            recovered["prompt"] = (
                "FACE-CROP SMILE REFINEMENT: Preserve this exact adult man's face "
                "shape, eyes, nose, dark hair, beard, clothing, raised open waving "
                "hand, full-body framing, and living room. Change only his expression "
                "to a warm, unmistakable practiced sitcom smile with natural gently "
                "upturned mouth corners and realistic cheeks. No open mouth, no large "
                "teeth, no object over the mouth, no duplicated face, no face seam.\\n\\n"
                + str(job.get("prompt") or "")
            )
        recovered["identity_control"] = {
            "version": "c001-smile-facedetailer-ipadapter-v5",
            "policy_revision": (
                "face-crop-strong-smile-guidance-v4"
                if v5_first_quality_failure else
                "face-crop-full-dependencies-repaired-v3"
                if v5_secondary_dependency_failure else
                "face-crop-dependencies-repaired-v2"
                if v5_dependency_failure else
                "face-crop-low-denoise-v1"
            ),
            "max_attempts": 1,
            "reason": (
                "the hard-clamped full-frame mouth mask had zero protected-face "
                "overlap but only about 11x7 latent pixels and synthesized a blue "
                "object over the mouth; refine the detected face at crop resolution"
                + (" after installing Impact Pack's missing declared piexif, "
                   "ultralytics, segment-anything, and dill dependencies"
                   if v5_secondary_dependency_failure else
                   " after installing Impact Pack's missing declared piexif and "
                   "ultralytics dependencies" if v5_dependency_failure else "")
            ),
            "edit_type": "smile_face_crop",
            "render_mode": "face_refine_identity",
            "identity_crop_fraction": [0.42, 0.05, 0.62, 0.38],
            "identity_anchor_path": str(original_anchor),
            "identity_weight": 0.70 if v5_first_quality_failure else 0.90,
            "face_detail_denoise": 0.42 if v5_first_quality_failure else 0.32,
            "recovery_index": int(recovery_index),
            "intermediate_reference": str(intermediate),
            "intermediate_reference_sha256": sha256(intermediate),
        }
    return recovered
'''

new2 = '''    if v4_failed:
        if v5_strong_smile_failure:
            # Handoff 2026-09-10: prior v4 closed-mouth negatives suppressed the
            # only unambiguous smile cue. One bounded tooth-bearing FaceDetailer
            # trial from the immutable wave intermediate.
            recovered["prompt"] = (
                "face-only portrait of the exact same adult man, clearly visible "
                "natural tooth-bearing friendly sitcom smile, warm practiced grin "
                "with visible upper teeth, upturned mouth corners, lifted cheeks, "
                "pleasant eyes, short dark-brown hair, natural brown beard, exact "
                "same identity"
            )
            recovered["negative"] = (
                "frown, scowl, stern expression, serious expression, angry, grimace, "
                "downturned mouth, pursed lips, closed mouth, sealed lips, blue object, "
                "object over mouth, mask, oversized teeth, deformed teeth, jagged teeth, "
                "duplicate face, face seam, different person, different beard, different hair"
            )
            recovered["denoise"] = 0.50
        elif v5_first_quality_failure:
            recovered["prompt"] = (
                "portrait detail of the same adult man, (warm friendly practiced "
                "sitcom smile:1.5), (relaxed naturally upturned mouth corners:1.4), "
                "subtly lifted cheeks, pleasant cheerful eyes, short dark-brown "
                "hair, natural brown beard and mustache, realistic skin, exact "
                "same identity"
            )
            recovered["negative"] = (
                "frown, scowl, stern expression, serious expression, angry, grimace, "
                "downturned mouth, pursed lips, blue object, object over mouth, mask, "
                "open mouth, oversized teeth, deformed teeth, duplicate face, face "
                "seam, different person, different beard, different hair"
            )
            recovered["denoise"] = 0.42
        else:
            recovered["prompt"] = (
                "FACE-CROP SMILE REFINEMENT: Preserve this exact adult man's face "
                "shape, eyes, nose, dark hair, beard, clothing, raised open waving "
                "hand, full-body framing, and living room. Change only his expression "
                "to a warm, unmistakable practiced sitcom smile with natural gently "
                "upturned mouth corners and realistic cheeks. No open mouth, no large "
                "teeth, no object over the mouth, no duplicated face, no face seam.\\n\\n"
                + str(job.get("prompt") or "")
            )
        if v5_strong_smile_failure:
            policy_revision = "face-crop-tooth-bearing-smile-v5"
            identity_weight = 0.58
            face_detail_denoise = 0.50
            reason_suffix = (
                "; prior strong-smile FaceDetailer guidance kept a closed mouth "
                "and stayed too subtle, so allow a natural tooth-bearing sitcom "
                "smile while still rejecting oversized/deformed teeth"
            )
        elif v5_first_quality_failure:
            policy_revision = "face-crop-strong-smile-guidance-v4"
            identity_weight = 0.70
            face_detail_denoise = 0.42
            reason_suffix = ""
        elif v5_secondary_dependency_failure:
            policy_revision = "face-crop-full-dependencies-repaired-v3"
            identity_weight = 0.90
            face_detail_denoise = 0.32
            reason_suffix = (
                " after installing Impact Pack's missing declared piexif, "
                "ultralytics, segment-anything, and dill dependencies"
            )
        elif v5_dependency_failure:
            policy_revision = "face-crop-dependencies-repaired-v2"
            identity_weight = 0.90
            face_detail_denoise = 0.32
            reason_suffix = (
                " after installing Impact Pack's missing declared piexif and "
                "ultralytics dependencies"
            )
        else:
            policy_revision = "face-crop-low-denoise-v1"
            identity_weight = 0.90
            face_detail_denoise = 0.32
            reason_suffix = ""
        recovered["identity_control"] = {
            "version": "c001-smile-facedetailer-ipadapter-v5",
            "policy_revision": policy_revision,
            "max_attempts": 1,
            "reason": (
                "the hard-clamped full-frame mouth mask had zero protected-face "
                "overlap but only about 11x7 latent pixels and synthesized a blue "
                "object over the mouth; refine the detected face at crop resolution"
                + reason_suffix
            ),
            "edit_type": "smile_face_crop",
            "render_mode": "face_refine_identity",
            "identity_crop_fraction": [0.42, 0.05, 0.62, 0.38],
            "identity_anchor_path": str(original_anchor),
            "identity_weight": identity_weight,
            "face_detail_denoise": face_detail_denoise,
            "recovery_index": int(recovery_index),
            "intermediate_reference": str(intermediate),
            "intermediate_reference_sha256": sha256(intermediate),
        }
    return recovered
'''

if old2 not in text:
    raise SystemExit("v4_failed FaceDetailer block not found exactly")
text = text.replace(old2, new2, 1)
path.write_text(text, encoding="utf-8")
py_compile.compile(str(path), doraise=True)
print("worker_patched_ok")
