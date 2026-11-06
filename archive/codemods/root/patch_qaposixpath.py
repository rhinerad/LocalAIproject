"""One-shot patch for 2026-09-24ab: split ComfyUI subfolders on both separators
in local_agent/tools.py and add the regression tests. Exact-match edits only;
aborts if any anchor is not found exactly once. Run from local_agent/."""
from pathlib import Path


def patch(path, edits):
    p = Path(path)
    text = p.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    for old, new in edits:
        old_n, new_n = old.replace("\n", nl), new.replace("\n", nl)
        count = text.count(old_n)
        assert count == 1, f"{path}: expected 1 match, found {count} for:\n{old[:160]}"
        text = text.replace(old_n, new_n)
    p.write_bytes(text.encode("utf-8"))
    print(f"patched {path} ({len(edits)} edits, newline={nl!r})")


# ---------------- tools.py ----------------
tools_edits = [
(
r'''def _resolve_story_still_outputs(manifest: dict | None) -> list[dict]:
    """Turn a complete image manifest into concrete file paths when possible."""
    if not isinstance(manifest, dict):
        return []
    outputs = manifest.get("outputs") or []
    if not isinstance(outputs, list):
        return []
    resolved: list[dict] = []
    comfy_root = ROOT / "outputs" / "stories" / "_comfy_output"
    for item in outputs:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        subfolder = str(item.get("subfolder") or "").strip()
        if not filename:
            continue
        path = comfy_root / subfolder / filename if subfolder else comfy_root / filename
        entry = {
''',
r'''def _split_comfy_subpath(value: object) -> list[str]:
    """Split a ComfyUI-reported ``subfolder``/``filename`` into path segments.

    ComfyUI reports ``subfolder`` with the separator of the machine it runs on
    ("stories\\Leo\\renders" from a Windows ComfyUI) and image_render stores that
    string verbatim in every manifest. pathlib only splits on the *running*
    interpreter's separator, so joining the raw string under a POSIX pathlib
    (Linux, WSL, macOS) keeps the backslashes as filename characters, is_file()
    is False, and the still QA reports not_run for a file that exists exactly
    where the manifest says (2026-09-24ab). Split on both separators so the
    lookup matches the manifest on either platform.
    """
    return [seg for seg in re.split(r"[\\/]+", str(value or "").strip()) if seg and seg != "."]


def _resolve_story_still_outputs(manifest: dict | None) -> list[dict]:
    """Turn a complete image manifest into concrete file paths when possible."""
    if not isinstance(manifest, dict):
        return []
    outputs = manifest.get("outputs") or []
    if not isinstance(outputs, list):
        return []
    resolved: list[dict] = []
    comfy_root = ROOT / "outputs" / "stories" / "_comfy_output"
    for item in outputs:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        subfolder = str(item.get("subfolder") or "").strip()
        if not filename:
            continue
        segments = _split_comfy_subpath(subfolder) + _split_comfy_subpath(filename)
        if not segments:
            continue
        path = comfy_root.joinpath(*segments)
        entry = {
'''),
(
r'''    paths = [Path(str(o["path"])) for o in outputs or [] if isinstance(o, dict) and o.get("path")]
    if not str(prompt or "").strip():
        record["error"] = "the render manifest has no prompt to check the still against"
        return record
    if not paths:
        record["error"] = "no rendered output file was found on disk to check"
        return record
''',
r'''    listed = [o for o in outputs or [] if isinstance(o, dict)]
    paths = [Path(str(o["path"])) for o in listed if o.get("path")]
    if not str(prompt or "").strip():
        record["error"] = "the render manifest has no prompt to check the still against"
        return record
    if not paths:
        # not_run means QA never got a file to look at. Say where it looked, so
        # a missing or mis-resolved output path reads as the problem it is
        # instead of looking like a QA verdict (2026-09-24ab).
        looked = [str(o.get("expected_path") or o.get("filename") or "") for o in listed]
        looked = [p for p in looked if p]
        if not listed:
            record["error"] = "the render manifest lists no output file to check"
        elif looked:
            record["error"] = ("no rendered output file was found on disk to check "
                               f"(looked for: {'; '.join(looked)})")
        else:
            record["error"] = "no rendered output file was found on disk to check"
        return record
'''),
]
patch("tools.py", tools_edits)

# ---------------- test file ----------------
test_edits = [
(
r'''from pathlib import Path
from unittest.mock import MagicMock, patch
''',
r'''from pathlib import Path, PurePosixPath
from unittest.mock import MagicMock, patch
'''),
(
r'''        self.assertEqual("not_run", qa["verdict"])
        fake.creative_approve.assert_not_called()

    def test_operator_approval_sets_continuity_anchor_for_next_still(self):
''',
r'''        self.assertEqual("not_run", qa["verdict"])
        fake.creative_approve.assert_not_called()
        # The record says where it looked, so a mis-resolved path is visible.
        self.assertIn("looked for", qa["error"])
        self.assertIn(str(png), qa["error"])

    def test_manifest_without_outputs_is_not_run_with_distinct_reason(self):
        fake = self._fake_qa()
        with patch.dict(sys.modules, {"creative_still_qa": fake}):
            qa = tools._story_still_qa([], prompt="an actor smiles", story="s4")
        self.assertEqual("not_run", qa["verdict"])
        self.assertIn("lists no output file", qa["error"])
        fake.creative_approve.assert_not_called()

    def test_resolver_finds_still_from_windows_or_posix_subfolder(self):
        # image_render stores ComfyUI's subfolder verbatim: backslashes from a
        # Windows ComfyUI (every real manifest under outputs/stories/), forward
        # slashes from a Linux one. Both must land on the same file whatever
        # pathlib flavour the checker runs under (fails on Linux/WSL without
        # the separator split in _resolve_story_still_outputs).
        png = self._complete_render("s5", "an actor smiles")
        manifest = json.loads((self.root / "outputs" / "stories" / "s5" / "manifests" /
                               "image_a.json").read_text(encoding="utf-8"))
        self.assertEqual("stories\\s5\\renders", manifest["outputs"][0]["subfolder"])
        for subfolder in ("stories\\s5\\renders", "stories/s5/renders", "stories\\s5/renders/"):
            variant = {**manifest, "outputs": [{**manifest["outputs"][0], "subfolder": subfolder}]}
            resolved = tools._resolve_story_still_outputs(variant)
            self.assertEqual(str(png), resolved[0]["path"], subfolder)
            self.assertEqual(str(png), resolved[0]["expected_path"], subfolder)
            self.assertEqual(subfolder, resolved[0]["subfolder"])

    def test_resolver_under_posix_pathlib_splits_windows_subfolder(self):
        # Models the failing platform on any host: a POSIX-flavoured root joins
        # "stories\\s6\\renders" as one literal segment unless the resolver
        # splits it. This is what made every still through story_image_job_status
        # report verdict=not_run ("no rendered output file was found on disk")
        # when this suite ran under a POSIX Python (2026-09-24u), while the
        # same code passed on Windows.
        expected = ("/srv/agent/outputs/stories/_comfy_output/stories/s6/renders/"
                    "image_a_00001_.png")
        files = {expected}

        class _PosixRoot(PurePosixPath):
            def is_file(self):
                return str(self) in files

        manifest = {"status": "complete", "outputs": [
            {"filename": "image_a_00001_.png", "subfolder": "stories\\s6\\renders",
             "type": "output"}]}
        with patch.object(tools, "ROOT", _PosixRoot("/srv/agent")):
            resolved = tools._resolve_story_still_outputs(manifest)
        self.assertEqual(expected, resolved[0]["expected_path"], resolved)
        self.assertEqual(expected, resolved[0]["path"], resolved)
        # And a still that really is missing names the path it looked for.
        files.clear()
        with patch.object(tools, "ROOT", _PosixRoot("/srv/agent")):
            qa = tools._story_still_qa(tools._resolve_story_still_outputs(manifest),
                                       prompt="an actor smiles", story="s6")
        self.assertEqual("not_run", qa["verdict"])
        self.assertIn(expected, qa["error"])

    def test_operator_approval_sets_continuity_anchor_for_next_still(self):
'''),
]
patch("test_story_stills_batch_review.py", test_edits)
