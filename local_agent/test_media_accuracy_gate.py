import tempfile
import unittest
from pathlib import Path

from PIL import Image

from media_accuracy_gate import (
    VIDEO_DIRECTOR_SCORE_KEYS,
    VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT,
    check_still,
    curriculum_threshold,
    parse_video_director_scores,
    prompt_assertions,
    semantic_verdict_from_caption,
    video_director_passes_curriculum,
    video_prompt_assertions,
)


def _gradient_png(path: Path, size=(1024, 768)) -> None:
    im = Image.new("RGB", size)
    px = im.load()
    w, h = size
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 255) // max(w - 1, 1), (y * 255) // max(h - 1, 1), 90)
    im.save(path)


class MediaAccuracyGateTests(unittest.TestCase):
    def test_scene_plate_viewpoint_does_not_require_camcorder_word(self):
        result = prompt_assertions(
            "Static ordinary apartment. Viewer-perspective framing. Clean scene plate.",
            "C001", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_semantic_verdict_requires_exact_structured_vlm(self):
        good = ('{"pass":true,"rationale":"Actor and apartment match.",'
                '"observed":{"subjects":["actor"],"setting":"apartment"},'
                '"checks":{"requested_subjects_present":true,'
                '"requested_pose_or_action_visible":true,"requested_composition_visible":true,'
                '"setting_matches":true,'
                '"identity_continuity":true,"no_forbidden_equipment":true,'
                '"blind_observation_consistent":true}}')
        r = semantic_verdict_from_caption(good, "apartment actor", model="qwen25-vl-nsfw-caption:v4-q4_k_m", runtime="llama.cpp")
        self.assertEqual(r["status"], "pass")
        bad = semantic_verdict_from_caption("A man in a room", "apartment actor", model="stub", runtime="ollama")
        self.assertEqual(bad["status"], "fail")

    def test_semantic_verdict_fails_without_prompt_checks_or_on_false_check(self):
        missing = '{"pass":true,"rationale":"Looks plausible.","observed":{"subjects":[],"setting":"room"}}'
        r = semantic_verdict_from_caption(missing, "actor points", model="qwen25-vl-nsfw-caption:v4-q4_k_m", runtime="llama.cpp")
        self.assertEqual(r["status"], "fail")
        false_check = ('{"pass":true,"rationale":"The actor is absent.",'
                       '"observed":{"subjects":[],"setting":"room"},'
                       '"checks":{"requested_subjects_present":false,'
                       '"requested_pose_or_action_visible":false,"requested_composition_visible":false,'
                       '"setting_matches":true,'
                       '"identity_continuity":false,"no_forbidden_equipment":true,'
                       '"blind_observation_consistent":false}}')
        r = semantic_verdict_from_caption(false_check, "actor points", model="qwen25-vl-nsfw-caption:v4-q4_k_m", runtime="llama.cpp")
        self.assertEqual(r["status"], "fail")
    def test_pass_and_hashes_remain_unapproved_without_semantic(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.png"
            _gradient_png(p)
            r = check_still(p, "Static ordinary apartment camcorder reference still", "C001", "start")
            self.assertEqual(r["status"], "pass")
            self.assertTrue(r["image_sha256"] and r["prompt_sha256"])
            self.assertEqual(r["semantic_check"], "not_run")
            self.assertEqual(r["qa_status"], "pending_semantic")
            self.assertEqual(r["approval_status"], "unapproved")

    def test_negated_camera_phrase_is_not_flagged_as_request(self):
        # "no visible recording camera" is a prohibition, not a request.
        # The gate must not reject the v5 qa_prompt on this basis.
        qa_prompt = (
            "Static 4:3 viewer-perspective reference still for image-to-video. One fictional adult man "
            "stands naturally in a non-action pose, fully visible head-to-toe with both white sneakers and "
            "floor beneath them inside the frame. He is near the center of a modest ordinary apartment "
            "living room with a visible sofa or couch. Realistic restrained late-1990s consumer-home-video "
            "texture. Clean scene plate: no visible recording camera, camcorder body, lens, tripod, "
            "operator, crew, or production equipment."
        )
        result = prompt_assertions(qa_prompt, "C001", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_video_prompt_requires_handheld_momentum(self):
        bad = video_prompt_assertions(
            "walk down a yellow hallway",
            camera_locked=False,
            scene_spec="damp yellow carpet hallway",
        )
        self.assertFalse(bad["pass"])
        self.assertTrue(any("handheld walking momentum" in r for r in bad["reasons"]))
        good = video_prompt_assertions(
            "[Handheld POV] yellow hallway. First-person camcorder tracking, "
            "heavy VHS artifacting, handheld walking momentum, continuous "
            "unbroken shot, realistic camera shake, 1990s home video aesthetic.",
            camera_locked=False,
            scene_spec="damp yellow carpet hallway",
        )
        self.assertTrue(good["pass"], good["reasons"])

    def test_rejects_motion_and_wrong_environment(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.png"
            _gradient_png(p)
            r = check_still(p, "Static Backrooms camcorder; actor walks", "C001", "start")
            self.assertEqual(r["status"], "fail")
            self.assertTrue(r["reasons"])
            self.assertEqual(r["semantic_check"], "not_run")
            self.assertEqual(r["approval_status"], "unapproved")

    def test_c016_last_generic_prompt_fails_mode_b_face_torso_language(self):
        generic = (
            "Static SDXL reference still for image-to-video, authentic 1990s consumer "
            "camcorder recording, 4:3 composition. Level 0 Backrooms, sickly yellow "
            "patterned wallpaper, damp brown-beige carpet. View through the actor's "
            "handheld camcorder from his physical position; the camcorder body, lens "
            "and operator are completely outside the frame. VISIBLE-SCENE RULE: clean "
            "scene plate showing only the fictional characters and environment."
        )
        result = prompt_assertions(generic, "C016", "last")
        self.assertFalse(result["pass"])
        self.assertIn(
            "Mode B still prompt missing face/torso hard reject language",
            result["reasons"],
        )

    def test_c016_last_floor_pov_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static low, slightly tilted 4:3 consumer-camcorder POV lying on the floor "
            "of an empty Level 0 Backrooms interior. Damp brown-beige carpet dominates "
            "the foreground under sickly yellow fluorescent light. Patterned yellow "
            "wallpaper, low acoustic ceiling tiles, rectangular fluorescent fixtures, "
            "and repetitive empty office openings are visible beyond the carpet. Do not "
            "depict the actor's face or torso. The actor is entirely outside the frame: "
            "no person, no hand, no sleeve, no body. No visible camera body, lens, "
            "tripod, operator, crew, apartment furniture, text, blood, or gore. The "
            "requested subject is the empty floor-level Backrooms environment itself; "
            "absence of a person or pose is correct."
        )
        result = prompt_assertions(qa_prompt, "C016", "last")
        self.assertTrue(result["pass"], result["reasons"])

    def test_mode_b_prohibitive_camera_list_is_not_a_positive_camera_request(self):
        prompt = (
            "Static 4:3 consumer-camcorder POV of an empty Level 0 Backrooms corner. "
            "Sickly yellow patterned wallpaper, damp brown-beige carpet, low acoustic "
            "ceiling tiles and fluorescent fixtures. Do not depict a face, torso, full "
            "body, visible camera body, lens, tripod, operator, crew, text, blood, or gore. "
            "No pose or action is requested; absence of a person is correct."
        )
        result = prompt_assertions(prompt, "C026", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c017_start_hand_press_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static low, slightly tilted 4:3 consumer-camcorder POV in an empty Level 0 "
            "Backrooms interior. Damp brown-beige carpet dominates the foreground; sickly "
            "yellow patterned walls, acoustic ceiling tiles and rectangular fluorescent "
            "lights are visible beyond it. Exactly one adult hand with a small olive-green "
            "overshirt cuff presses into the damp carpet at the extreme lower edge. The "
            "actor is otherwise entirely outside the frame: do not depict the actor's face "
            "or torso. No visible camera body, lens, tripod, operator, crew, full body, "
            "other person, apartment furniture, text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C017", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c017_last_wallpaper_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static low 4:3 consumer-camcorder POV turned toward a nearby Level 0 "
            "Backrooms wall. Repetitive sickly yellow patterned wallpaper fills most of "
            "the frame under fluorescent light. A strip of damp brown-beige carpet and "
            "a simple baseboard remain along the bottom. Do not depict the actor's face "
            "or torso. The actor is entirely outside the frame: no person, no hand, no "
            "sleeve, no body. No visible camera body, lens, tripod, operator, crew, "
            "apartment furniture, text, blood, or gore. The requested subject is the "
            "yellow wallpaper wall; absence of a person or pose is correct."
        )
        result = prompt_assertions(qa_prompt, "C017", "last")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c018_start_hand_wallpaper_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static close 4:3 consumer-camcorder POV of a Level 0 Backrooms wall. "
            "Repetitive sickly yellow patterned wallpaper fills most of the frame; a "
            "strip of damp brown-beige carpet remains along the bottom. Exactly one "
            "adult hand with a small olive-green overshirt cuff presses into the yellow "
            "wallpaper. The actor is otherwise entirely outside the frame: do not depict "
            "the actor's face or torso. No visible camera body, lens, tripod, operator, "
            "crew, full body, other person, apartment furniture, text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C018", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c018_last_hand_pullback_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static 4:3 consumer-camcorder POV of a Level 0 Backrooms wall. Repetitive "
            "sickly yellow patterned wallpaper fills most of the frame; a strip of damp "
            "brown-beige carpet remains along the bottom. Exactly one adult hand with a "
            "small olive-green overshirt cuff pulls back from the wallpaper, with visible "
            "moisture on the fingers. The actor is otherwise entirely outside the frame: "
            "do not depict the actor's face or torso. No visible camera body, lens, "
            "tripod, operator, crew, full body, other person, apartment furniture, text, "
            "blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C018", "last")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c019_start_chest_cuff_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static chest-height 4:3 consumer-camcorder POV looking forward into an empty "
            "Level 0 Backrooms room. Sickly yellow patterned wallpaper, damp brown-beige "
            "carpet, acoustic ceiling tiles, rectangular fluorescent lights, and repetitive "
            "empty openings are visible. The requested subject is a small olive-green sleeve "
            "cuff at the extreme lower edge. Do not depict the actor's face, torso, palm, or "
            "fingers. The actor is otherwise entirely outside the frame. No visible camera "
            "body, lens, tripod, operator, crew, full body, other person, apartment "
            "furniture, text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C019", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c019_last_three_openings_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static chest-height 4:3 consumer-camcorder POV turned toward a Level 0 "
            "Backrooms wall with three identical empty rectangular openings side by side. "
            "Sickly yellow patterned wallpaper, damp brown-beige carpet, and rectangular "
            "fluorescent lights are visible. A small olive-green sleeve cuff at the lower "
            "edge is allowed. Do not depict the actor's face or torso. The actor is "
            "otherwise entirely outside the frame. No visible camera body, lens, tripod, "
            "operator, crew, full body, other person, apartment furniture, text, blood, "
            "or gore. The requested subject is the three identical openings."
        )
        result = prompt_assertions(qa_prompt, "C019", "last")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c020_start_three_openings_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static chest-height 4:3 consumer-camcorder POV of three identical yellow "
            "doorless openings with fluorescent fixtures repeating overhead. Sickly yellow "
            "patterned wallpaper and damp brown-beige carpet are visible. The requested "
            "subjects are the three identical openings and repeating fluorescents. A small "
            "olive-green sleeve cuff at the lower edge is allowed and is not a face or "
            "torso. Do not depict the actor's face or torso. No pose or action is "
            "requested. No visible camera body, lens, tripod, operator, crew, full body, "
            "other person, apartment furniture, text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C020", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c020_last_center_opening_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static chest-height 4:3 consumer-camcorder POV advanced into the center "
            "yellow doorless opening, with walls closing in on the left and right. Sickly "
            "yellow patterned wallpaper, damp brown-beige carpet, and fluorescent lights "
            "are visible ahead. The requested subject is the center opening with closing "
            "walls. A small olive-green sleeve cuff at the lower edge is allowed and is "
            "not a face or torso. Do not depict the actor's face or torso. No pose or "
            "action is requested. No visible camera body, lens, tripod, operator, crew, "
            "full body, legs, feet, other person, apartment furniture, text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C020", "last")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c021_start_narrow_corridor_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static low 4:3 consumer-camcorder POV moving forward through a narrow Level 0 "
            "Backrooms corridor. Damp brown-beige carpet fills the lower frame; sickly yellow "
            "patterned wallpaper fills the left and right. Fluorescent lights recede overhead. "
            "The requested subject is the narrow yellow corridor with floor and wallpaper "
            "filling the frame. A small olive-green sleeve cuff at the lower edge is allowed "
            "and is not a face or torso. Do not depict the actor's face or torso. No pose or "
            "action is requested. No visible camera body, lens, tripod, operator, crew, full "
            "body, legs, feet, other person, apartment furniture, text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C021", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c021_last_look_back_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static 4:3 consumer-camcorder POV looking back down a narrow Level 0 "
            "Backrooms corridor. Sickly yellow patterned wallpaper on both sides, damp "
            "brown-beige carpet, fluorescent lights receding. The requested subject is the "
            "corridor behind. A small olive-green sleeve or shoulder fragment at the edge "
            "is allowed and is not a face or torso. Do not depict the actor's face or "
            "torso. No pose or action is requested. No visible camera body, lens, tripod, "
            "operator, crew, full body, other person, doors with knobs, exit signs, "
            "apartment furniture, text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C021", "last")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c022_start_empty_corridor_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static 4:3 consumer-camcorder POV of an empty ordinary Level 0 Backrooms "
            "corridor ahead. Sickly yellow patterned wallpaper, damp brown-beige carpet, "
            "fluorescent lights receding. The requested subject is the empty corridor. A "
            "small olive-green sleeve cuff at the lower edge is allowed and is not a face "
            "or torso. Do not depict the actor's face or torso. No pose or action is "
            "requested. No visible camera body, lens, tripod, operator, crew, full body, "
            "other person, apartment furniture, text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C022", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c022_last_longer_corridor_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static 4:3 consumer-camcorder POV of the same empty Level 0 Backrooms "
            "corridor, now subtly longer and more distant. Sickly yellow patterned "
            "wallpaper, damp brown-beige carpet, more repeating fluorescent lights "
            "receding to a farther end wall. The requested subject is the longer "
            "corridor. A small olive-green sleeve cuff at the lower edge is allowed and "
            "is not a face or torso. Do not depict the actor's face or torso. No pose or "
            "action is requested. No visible camera body, lens, tripod, operator, crew, "
            "full body, other person, apartment furniture, text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C022", "last")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c023_start_gesturing_hand_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static 4:3 consumer-camcorder POV looking back down a narrow Level 0 "
            "Backrooms corridor. Sickly yellow patterned wallpaper, damp brown-beige "
            "carpet, fluorescent lights receding. Exactly one adult hand with a small "
            "olive-green overshirt cuff gestures into the lower frame. The actor is "
            "otherwise entirely outside the frame: do not depict the actor's face or "
            "torso. No visible camera body, lens, tripod, operator, crew, full body, "
            "legs, feet, other person, apartment furniture, text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C023", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c023_last_hand_slap_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static slightly tilted 4:3 consumer-camcorder POV after a lurch, looking "
            "down a Level 0 Backrooms corridor. Exactly one adult hand with a small "
            "olive-green overshirt cuff slaps against the yellow patterned wallpaper for "
            "balance. The actor is otherwise entirely outside the frame: do not depict "
            "the actor's face or torso. No visible camera body, lens, tripod, operator, "
            "crew, full body, legs, feet, other person, apartment furniture, text, blood, "
            "or gore."
        )
        result = prompt_assertions(qa_prompt, "C023", "last")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c024_start_branching_corridor_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static steadied 4:3 consumer-camcorder POV looking down a branching Level 0 "
            "Backrooms corridor. Sickly yellow patterned wallpaper, damp brown-beige carpet, "
            "fluorescent lights, and a split or crossing of yellow hallways ahead. The "
            "requested subject is the branching corridor. A small olive-green sleeve cuff "
            "at the lower edge is allowed and is not a face or torso. Do not depict the "
            "actor's face or torso. No pose or action is requested. No visible camera body, "
            "lens, tripod, operator, crew, full body, other person, apartment furniture, "
            "text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C024", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c024_last_flickering_passage_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static 4:3 consumer-camcorder POV turned toward a Level 0 Backrooms passage "
            "with one flickering fluorescent light. Sickly yellow patterned wallpaper, damp "
            "brown-beige carpet, a darker passage ahead. The requested subject is the "
            "flickering-light passage. A small olive-green sleeve cuff at the lower edge is "
            "allowed and is not a face or torso. Do not depict the actor's face or torso. "
            "No pose or action is requested. No visible camera body, lens, tripod, operator, "
            "crew, full body, other person, apartment furniture, text, blood, or gore."
        )
        result = prompt_assertions(qa_prompt, "C024", "last")
        self.assertTrue(result["pass"], result["reasons"])

    def test_c025_corridor_qa_prompts_pass_mode_b_assertions(self):
        start = (
            "Static 4:3 consumer-camcorder POV of a long Level 0 Backrooms corridor with "
            "repeating yellow wallpaper and damp brown-beige carpet. Fluorescent lights "
            "recede overhead. The requested subject is the long yellow corridor. A small "
            "olive-green sleeve cuff at the lower edge is allowed and is not a face or "
            "torso. Do not depict the actor's face or torso. No pose or action is "
            "requested. No visible camera body, lens, tripod, operator, crew, full body, "
            "other person, apartment furniture, text, blood, or gore."
        )
        last = (
            "Static 4:3 consumer-camcorder POV of a long Level 0 Backrooms corridor "
            "stretching into the distance, fluorescent lights repeating toward a vanishing "
            "point. Sickly yellow patterned wallpaper and damp brown-beige carpet. The "
            "requested subject is the vanishing corridor. A small olive-green sleeve cuff "
            "at the lower edge is allowed and is not a face or torso. Do not depict the "
            "actor's face or torso. No pose or action is requested. No visible camera body, "
            "lens, tripod, operator, crew, full body, other person, apartment furniture, "
            "text, blood, or gore."
        )
        self.assertTrue(prompt_assertions(start, "C025", "start")["pass"])
        self.assertTrue(prompt_assertions(last, "C025", "last")["pass"])

    def test_c027_start_close_wall_qa_prompt_passes_mode_b_assertions(self):
        qa_prompt = (
            "Static close 4:3 consumer-camcorder POV of a Level 0 Backrooms wall. "
            "Sickly yellow chevron wallpaper fills most of the frame under one "
            "flickering fluorescent light. A small olive-green sleeve cuff at the "
            "lower edge is allowed and is not a face or torso. Do not depict the "
            "actor's face or torso. No pose or action is requested. No visible camera "
            "body, lens, tripod, operator, crew, full body, other person, apartment "
            "furniture, text, blood, or gore. The requested subject is the close "
            "yellow-lit wall and flickering light."
        )
        result = prompt_assertions(qa_prompt, "C027", "start")
        self.assertTrue(result["pass"], result["reasons"])

    def test_video_director_system_prompt_requires_three_float_axes(self):
        prompt = VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT
        for key in VIDEO_DIRECTOR_SCORE_KEYS:
            self.assertIn(key, prompt)
        self.assertIn("JSON number", prompt)
        self.assertIn("Do not include a boolean pass field", prompt)
        self.assertNotIn("```", prompt)

    def test_curriculum_tightens_from_060_to_080(self):
        self.assertEqual(curriculum_threshold(0), 0.60)
        self.assertEqual(curriculum_threshold(2), 0.60)
        self.assertEqual(curriculum_threshold(3), 0.70)
        self.assertEqual(curriculum_threshold(6), 0.80)
        # Strict bar lowered 0.85 -> 0.80 (2026-09-24): the fixed judge scores
        # correct Backrooms clips at aesthetic 0.80-0.85.
        self.assertEqual(curriculum_threshold(9), 0.80)
        self.assertEqual(curriculum_threshold(99), 0.80)

    def test_curriculum_strict_bar_admits_080_minimum(self):
        parsed = parse_video_director_scores(
            '{"text_video_alignment":1.0,"temporal_consistency":1.0,'
            '"aesthetic_quality":0.80,"rationale":{}}',
            "backrooms hallway",
            model="qwen25-vl-nsfw-caption:v4-q4_k_m", runtime="llama.cpp",
        )
        self.assertEqual(parsed["minimum"], 0.80)
        strict = video_director_passes_curriculum(parsed, 99)
        self.assertTrue(strict["pass"])
        self.assertEqual(strict["threshold"], 0.80)

    def test_parse_video_director_scores_accepts_json_floats(self):
        caption = (
            '{"text_video_alignment":0.72,"temporal_consistency":0.81,'
            '"aesthetic_quality":0.66,'
            '"rationale":{"text_video_alignment":"Subjects match.",'
            '"temporal_consistency":"Identity holds.",'
            '"aesthetic_quality":"Slightly soft."}}'
        )
        parsed = parse_video_director_scores(
            caption, "drone cliffs",
            model="qwen25-vl-nsfw-caption:v4-q4_k_m", runtime="llama.cpp",
        )
        self.assertEqual(parsed["status"], "pass")
        self.assertEqual(parsed["scores"]["text_video_alignment"], 0.72)
        self.assertEqual(parsed["minimum"], 0.66)
        self.assertEqual(parsed["mean"], 0.73)
        early = video_director_passes_curriculum(parsed, 0)
        self.assertTrue(early["pass"])
        late = video_director_passes_curriculum(parsed, 9)
        self.assertFalse(late["pass"])
        self.assertEqual(late["threshold"], 0.80)

    def test_parse_video_director_scores_fail_closed(self):
        prose = parse_video_director_scores(
            "looks pretty good", model="qwen25-vl-nsfw-caption:v4-q4_k_m",
            runtime="llama.cpp",
        )
        self.assertEqual(prose["status"], "fail")
        wrong_runtime = parse_video_director_scores(
            '{"text_video_alignment":1,"temporal_consistency":1,"aesthetic_quality":1}',
            model="stub", runtime="ollama",
        )
        self.assertEqual(wrong_runtime["status"], "fail")
        percent = parse_video_director_scores(
            '{"text_video_alignment":"72%","temporal_consistency":0.8,'
            '"aesthetic_quality":0.9}',
            model="qwen25-vl-nsfw-caption:v4-q4_k_m", runtime="llama.cpp",
        )
        self.assertEqual(percent["status"], "pass")
        self.assertEqual(percent["scores"]["text_video_alignment"], 0.72)


if __name__ == "__main__":
    unittest.main()
