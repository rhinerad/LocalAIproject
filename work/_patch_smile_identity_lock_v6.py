from pathlib import Path
import py_compile

path = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\work\run_prompt_pack_production.py")
text = path.read_text(encoding="utf-8")

old = '''    v5_strong_smile_failure = policy_failure_count(
        attempt_root, "c001-smile-facedetailer-ipadapter-v5",
        "face-crop-strong-smile-guidance-v4",
    ) >= 1
    recovered["qa_prompt"] = str(job.get("qa_prompt") or job.get("prompt") or "")
'''
new = '''    v5_strong_smile_failure = policy_failure_count(
        attempt_root, "c001-smile-facedetailer-ipadapter-v5",
        "face-crop-strong-smile-guidance-v4",
    ) >= 1
    v5_tooth_bearing_failure = policy_failure_count(
        attempt_root, "c001-smile-facedetailer-ipadapter-v5",
        "face-crop-tooth-bearing-smile-v5",
    ) >= 1
    recovered["qa_prompt"] = str(job.get("qa_prompt") or job.get("prompt") or "")
'''
if old not in text:
    raise SystemExit('failure count block missing')
text = text.replace(old, new, 1)

old2 = '''        if v5_strong_smile_failure:
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
'''
new2 = '''        if v5_tooth_bearing_failure:
            # 2026-09-10e: tooth-bearing at denoise 0.50 / IP 0.58 produced a smile
            # but broke blind continuity (same_person/hair/facial_hair). Reassess:
            # keep tooth-bearing smile, raise identity lock, lower denoise.
            recovered["prompt"] = (
                "face-only portrait of the EXACT same adult man from the reference, "
                "identical short dark-brown hair, identical natural brown beard and "
                "mustache, identical face shape and eyes, clearly visible natural "
                "tooth-bearing friendly sitcom smile with visible upper teeth, "
                "upturned mouth corners, lifted cheeks, pleasant eyes"
            )
            recovered["negative"] = (
                "frown, scowl, stern expression, serious expression, angry, grimace, "
                "downturned mouth, pursed lips, closed mouth, sealed lips, blue object, "
                "object over mouth, mask, oversized teeth, deformed teeth, jagged teeth, "
                "duplicate face, face seam, different person, different beard, different "
                "hair, different face shape, younger face, cleaner shaven, long hair"
            )
            recovered["denoise"] = 0.42
        elif v5_strong_smile_failure:
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
'''
if old2 not in text:
    raise SystemExit('prompt branch missing')
text = text.replace(old2, new2, 1)

old3 = '''        if v5_strong_smile_failure:
            policy_revision = "face-crop-tooth-bearing-smile-v5"
            identity_weight = 0.58
            face_detail_denoise = 0.50
            reason_suffix = (
                "; prior strong-smile FaceDetailer guidance kept a closed mouth "
                "and stayed too subtle, so allow a natural tooth-bearing sitcom "
                "smile while still rejecting oversized/deformed teeth"
            )
        elif v5_first_quality_failure:
'''
new3 = '''        if v5_tooth_bearing_failure:
            policy_revision = "face-crop-tooth-bearing-identity-lock-v6"
            identity_weight = 0.80
            face_detail_denoise = 0.42
            reason_suffix = (
                "; prior tooth-bearing FaceDetailer trial (denoise 0.50 / IP 0.58) "
                "broke blind continuity on person/hair/beard, so raise identity "
                "lock and lower denoise while keeping a tooth-bearing sitcom smile"
            )
        elif v5_strong_smile_failure:
            policy_revision = "face-crop-tooth-bearing-smile-v5"
            identity_weight = 0.58
            face_detail_denoise = 0.50
            reason_suffix = (
                "; prior strong-smile FaceDetailer guidance kept a closed mouth "
                "and stayed too subtle, so allow a natural tooth-bearing sitcom "
                "smile while still rejecting oversized/deformed teeth"
            )
        elif v5_first_quality_failure:
'''
if old3 not in text:
    raise SystemExit('policy_revision branch missing')
text = text.replace(old3, new3, 1)

path.write_text(text, encoding='utf-8')
py_compile.compile(str(path), doraise=True)
print('patched_v6_ok')
