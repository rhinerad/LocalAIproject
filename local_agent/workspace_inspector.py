"""Read-only project-root classifier for general local-agent chats.

It reports evidence, not authority: callers must still select a workspace for
their new chat, and this module can never select a model, edit a file, or start
a render.  Equal Shares is recognized only by distinctive on-disk markers;
generic ComfyUI/video/prompt language is intentionally not enough.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

MAX_LISTED_DOCS = 12


def _present(root: Path, names: tuple[str, ...]) -> list[str]:
    return [name for name in names if (root / name).is_file()]


def inspect(path: str | Path) -> dict[str, Any]:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("workspace root is not an existing directory")
    names = {item.name.lower() for item in root.iterdir()}
    evidence: list[str] = []
    docs: list[str] = []
    kind, confidence = "general_folder", "candidate"
    equal_markers = ((root / "docs" / "GOLDEN_REFERENCE" / "PROVEN_FACTS.md").is_file()
                     and (root / "outputs" / "equal_shares").is_dir())
    if equal_markers or root.name == "COMFYUI_STORY_HANDOFF_2026-08-09":
        kind, confidence = "equal_shares", "unambiguous"
        evidence.append("distinctive Equal Shares documentation/output markers")
        docs = [name for name in (
            "CLAUDE.md", "docs/GOLDEN_REFERENCE/PROVEN_FACTS.md",
            "docs/GOLDEN_REFERENCE/README.md", "docs/H3_PROMPT_RULES.md",
        ) if (root / name).is_file()]
    elif (root / "adapter_config.json").is_file() or (root / "dataset_info.json").is_file() or {"lora", "datasets", "dataset"} & names:
        kind = "dataset_or_lora"
        evidence.extend(_present(root, ("adapter_config.json", "dataset_info.json", "README.md")))
        docs = _present(root, ("README.md", "dataset_card.md", "adapter_config.json"))
    elif (root / "custom_nodes").is_dir() and ((root / "user").is_dir() or "comfyui" in root.name.lower()):
        kind = "comfyui_project"
        evidence.extend(["custom_nodes/", "user/" if (root / "user").is_dir() else "ComfyUI-named root"])
        docs = _present(root, ("README.md", "extra_model_paths.yaml", "requirements.txt"))
    elif (root / ".git").exists() or {"pyproject.toml", "package.json", "cargo.toml", "go.mod"} & names:
        kind = "code_repository"
        evidence.extend(_present(root, ("pyproject.toml", "package.json", "Cargo.toml", "go.mod")))
        if (root / ".git").exists():
            evidence.append(".git")
        docs = _present(root, ("README.md", "CONTRIBUTING.md", "pyproject.toml", "package.json"))
    if not docs:
        docs_dir = root / "docs"
        if docs_dir.is_dir():
            docs = [str(item.relative_to(root)) for item in sorted(docs_dir.glob("*.md"))[:MAX_LISTED_DOCS]]
    return {
        "root": str(root), "detected_project_type": kind,
        "detection_confidence": confidence, "evidence": evidence[:MAX_LISTED_DOCS],
        "authoritative_docs": docs[:MAX_LISTED_DOCS],
        "note": "Read-only inspection only. Select a workspace explicitly; detection never changes chat scope or grants an action.",
    }
