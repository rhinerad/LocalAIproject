from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
LOCAL_AGENT = ROOT / "local_agent"
MEMORY_FILE = LOCAL_AGENT / "memory.json"


def update_memory() -> None:
    data = json.loads(MEMORY_FILE.read_text(encoding="utf8"))
    facts = data.setdefault("facts", [])
    forgotten = data.setdefault("_forgotten", [])
    next_id = max([int(x.get("id", -1)) for x in facts + forgotten], default=-1) + 1

    entries = [
        (
            "goal",
            "[Architecture][Context-Optimization][Token-Pruning][Memory-Pipeline] Pillar 1: "
            "add a CPU-side rolling summarizer in local_agent/context_compactor.py using "
            "llama3.1:8b on router.CPU_HOST with keep_alive=\"0\" and strict JSON output for "
            "goal, decisions, open_questions, tool_state, hard_constraints, and notable_files.",
        ),
        (
            "goal",
            "[Architecture][Context-Optimization][Token-Pruning][Memory-Pipeline] Pillar 2: "
            "add local_agent/artifacts.py to spill oversized tool outputs to "
            "runtime/artifacts/{id}.json with SHA-1 fingerprinting and replace live prompt "
            "content with a lightweight artifact pointer when output exceeds the cap.",
        ),
        (
            "goal",
            "[Architecture][Context-Optimization][Token-Pruning][Memory-Pipeline] Pillar 3: "
            "add asynchronous post-turn memory extraction in local_agent/memory_extractor.py "
            "and call memory.remember() only for stable, non-sensitive operator facts/preferences "
            "gathered after the turn completes.",
        ),
        (
            "goal",
            "[Architecture][Context-Optimization][Token-Pruning][Memory-Pipeline] Pillar 4: "
            "add local_agent/prompt_prefix.py with @lru_cache(maxsize=128) and keep static "
            "prompt prefix ordering byte-stable in local_agent/agent.py to improve local "
            "KV-cache reuse.",
        ),
        (
            "goal",
            "[Architecture][Context-Optimization][Token-Pruning][Memory-Pipeline] Router bug fix: "
            "local_agent/router.py::decide() must block on /api/ps until the 14B model is fully "
            "evicted from VRAM before CPU fallback; skip_gpu_inventory must not suppress unloading.",
        ),
    ]

    for category, text in entries:
        facts.append(
            {
                "id": next_id,
                "category": category,
                "text": text,
                "fp": "",
                "added": "2026-08-27",
            }
        )
        next_id += 1

    MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf8")


def update_chroma() -> None:
    import sys

    sys.path.insert(0, str(LOCAL_AGENT))
    import chromadb  # type: ignore
    from chromadb.config import Settings  # type: ignore
    import ollama_client as oll  # type: ignore

    db = LOCAL_AGENT / "exemplar_store" / "chroma"
    client = chromadb.PersistentClient(
        path=str(db),
        settings=Settings(anonymized_telemetry=False),
    )
    col = client.get_or_create_collection(
        "context_optimization_audit_notes",
        metadata={"hnsw:space": "cosine"},
    )
    tag_str = "[Architecture],[Context-Optimization],[Token-Pruning],[Memory-Pipeline]"
    docs = [
        (
            "pillar_1_context_compactor",
            "Pillar 1: secondary LLM context compactor. Use llama3.1:8b on router.CPU_HOST "
            "with keep_alive=\"0\" to summarize old messages into strict JSON fields for goal, "
            "decisions, open_questions, tool_state, hard_constraints, and notable_files.",
        ),
        (
            "pillar_2_artifact_pruning",
            "Pillar 2: artifact registry and tool pruning. Spill oversized tool outputs to "
            "runtime/artifacts/{id}.json with SHA-1 fingerprinting and replace the live prompt "
            "payload with a lightweight pointer when text exceeds 2400 characters.",
        ),
        (
            "pillar_3_memory_extraction",
            "Pillar 3: autonomous memory extraction. Run post-turn CPU-only extraction and "
            "feed only stable, non-sensitive operator facts/preferences into memory.remember().",
        ),
        (
            "pillar_4_prompt_prefix",
            "Pillar 4: byte-stable prompt prefix memoization. Memoize stable prefix blocks with "
            "@lru_cache(maxsize=128) and keep system/memory ordering deterministic to improve "
            "local KV-cache reuse.",
        ),
        (
            "router_vram_eviction_fix",
            "Router bug fix: router.py::decide() must not let skip_gpu_inventory suppress GPU "
            "eviction. Block on /api/ps until the 14B model is fully unloaded before CPU fallback.",
        ),
    ]

    embeddings = oll.embed([doc for _, doc in docs], model="nomic-embed-text:latest", host=oll.HOST)
    col.upsert(
        ids=[doc_id for doc_id, _ in docs],
        documents=[doc for _, doc in docs],
        embeddings=embeddings,
        metadatas=[
            {
                "tags": tag_str,
                "category": "architecture",
                "status": "pending_patch",
                "topic": doc_id,
            }
            for doc_id, _ in docs
        ],
    )


if __name__ == "__main__":
    update_memory()
    update_chroma()
    print("updated memory.json and Chroma collection context_optimization_audit_notes")
