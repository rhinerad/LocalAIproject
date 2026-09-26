"""Allow-listed background tasks. No arbitrary command or file-path task exists."""
from __future__ import annotations

import os
import platform
import socket
import sys
import time
from pathlib import Path

from .celery_app import app
from .farm_core import EncryptedArtifactStore, distill_review_candidates
from .job_registry import JobRegistry
from . import judge_rubric

# local_agent/'s own modules (context_compactor, ollama_client, router) use
# flat imports (e.g. `from atomic_io import ...`), matching how agent.py and
# the interactive server run -- not relative-package imports. A worker
# process launched fresh on a secondary machine has no guarantee local_agent/
# itself is already on sys.path (only the repo root is, via `-m celery ...
# local_agent.worker_farm.celery_app:app`), so this inserts it explicitly at
# call time -- same defensive pattern tools.py's forget_fact() already uses.
_LOCAL_AGENT_DIR = str(Path(__file__).resolve().parent.parent)


def _use_local_agent_imports() -> None:
    if _LOCAL_AGENT_DIR not in sys.path:
        sys.path.insert(0, _LOCAL_AGENT_DIR)


# Celery prefork MainProcess imports this module (celery_app include=) but
# never runs _embed_chunks, so ollama_client used to be imported only in the
# worker fork. When embed_chunks raised OllamaUnavailable, MainProcess then
# crashed with ModuleNotFoundError while unpickling/repr'ing the exception
# and wedged the consumer. Import at module load so MainProcess can handle it.
_use_local_agent_imports()
import ollama_client as _ollama_client  # noqa: E402,F401


def _run_distill(envelope: dict) -> dict:
    registry = JobRegistry()
    claimed, record = registry.claim(envelope["job_id"])
    if not claimed:
        return {"job_id": record["job_id"], "status": record["state"], "deduplicated": True}
    try:
        result = distill_review_candidates(envelope)
        result_id = f"result_{envelope['job_id']}"
        EncryptedArtifactStore().write_json(result_id, result)
        registry.complete(envelope["job_id"], result_id)
        return {"job_id": result["job_id"], "status": result["status"], "candidate_count": len(result["candidates"]), "deduplicated": False}
    except OSError as exc:
        # Keep the durable ledger claimable for Celery's bounded retry.  This
        # is deliberately distinct from a permanent task failure.
        registry.requeue(envelope["job_id"], type(exc).__name__)
        raise
    except Exception as exc:
        registry.fail(envelope["job_id"], type(exc).__name__)
        raise


# Per-worker model choice (worker_farm/README.md): the model this task uses
# is this worker's own environment setting, not a fleet-wide constant.
# Defaults to context_compactor's workstation default (llama3.1:8b) only if
# the worker's environment doesn't say otherwise. mac_worker is recorded
# (2026-09-02) to run a Mistral Nemo abliterated build instead -- set
# FARM_SUMMARIZE_MODEL in that worker's own launch environment, do not
# hardcode a Mac-specific model into this shared file, another future
# worker may want a different one again.
_SUMMARIZE_MODEL_ENV = "FARM_SUMMARIZE_MODEL"
# Background farm jobs aren't racing an interactive turn the way the
# workstation's compaction is, so this uses a much longer timeout than
# context_compactor's own 12s interactive default -- a slower CPU-only
# worker (e.g. a 2019 Intel MacBook Pro) legitimately needs more time.
_SUMMARIZE_TIMEOUT_S = 120


def _summarize_messages(messages: list[dict]) -> dict:
    """Runs context_compactor's existing compaction against whatever local
    CPU model this worker machine is configured for -- per
    worker_farm/README.md's "per-worker model choice" policy, that model
    may or may not actually be installed yet. Absence is a normal,
    reportable outcome, not an error."""
    _use_local_agent_imports()
    import context_compactor
    model = os.environ.get(_SUMMARIZE_MODEL_ENV, context_compactor.MODEL)
    summary = context_compactor.summarize_old_messages(
        messages, model=model, timeout=_SUMMARIZE_TIMEOUT_S)
    if summary is None:
        return {"summarized": False, "model_expected": model,
                "note": f"configured summarizer model ({model}) not installed "
                        "or unreachable on this worker -- see "
                        "worker_farm/README.md's known-worker-machines table"}
    return {"summarized": True, "summary": summary, "model": model}


def _embed_chunks(chunks: list[dict]) -> dict:
    """Stateless: embeds whatever {id, text} chunks are in the envelope and
    returns {id: vector}. Does not read or write retrieval.py's on-disk
    embedding cache (knowledge/retrieval_embeddings.json) -- that cache is
    workstation-local; merging a worker's results into it is the caller's
    job, not this task's. Mirrors judge_transcript's "operate on the
    envelope, return findings directly" simplicity."""
    _use_local_agent_imports()
    import ollama_client as oll
    import router
    ids = [str(c.get("id", "")) for c in chunks]
    texts = [str(c.get("text", "")) for c in chunks]
    if not texts:
        return {"vectors": {}, "model": None, "note": "no chunks supplied"}
    vectors = oll.embed(texts, model="nomic-embed-text:latest", host=router.CPU_HOST)
    if len(vectors) != len(ids):
        raise ValueError("embedding count did not match chunk count")
    return {"vectors": dict(zip(ids, vectors)), "model": "nomic-embed-text:latest"}


_QWYTHOS_MODEL_ENV = "FARM_QWYTHOS_MODEL"
_QWYTHOS_HOST = os.environ.get("FARM_OLLAMA_HOST", "127.0.0.1:11434")
_QWYTHOS_TIMEOUT_S = 90
# Match the GPU-tier CPU Ollama server (START_LOCAL_AGENT_GUI.ps1
# $CpuOnly OLLAMA_KEEP_ALIVE=30m). Per-request keep_alive must not be
# shorter than the daemon default, or a back-to-back farm turn reloads.
_QWYTHOS_KEEP_ALIVE = "30m"


def _qwythos_evaluate(envelope: dict) -> dict:
    """Lightweight tool-calling turn on this worker's local Ollama.

    Unloads the summarize model first when it is resident — 2026-09-04h
    measured Qwythos + mistral-nemo + nomic-embed at 14.1 GB on the 16 GB
    Mac, which swapped. Embed (274 MB) may stay; summarize may not.
    """
    _use_local_agent_imports()
    import ollama_client as oll
    import router
    messages = envelope.get("messages") or []
    tools = envelope.get("tools") or None
    if not isinstance(messages, list) or not messages:
        raise ValueError("qwythos_evaluate envelope needs a non-empty messages list")
    model = os.environ.get(_QWYTHOS_MODEL_ENV, router.QWYTHOS_MODEL)
    summarize = os.environ.get(_SUMMARIZE_MODEL_ENV, "")
    resident = router._running_models(_QWYTHOS_HOST) or []
    for name in resident:
        if summarize and router._is_configured_variant(name, summarize):
            router.unload(_QWYTHOS_HOST, name)
    text, calls = oll.chat(
        messages, model=model, host=_QWYTHOS_HOST, timeout=_QWYTHOS_TIMEOUT_S,
        tools=tools or None, keep_alive=_QWYTHOS_KEEP_ALIVE,
        options={"num_gpu": 0, "num_thread": 4, "num_ctx": 8192,
                 "temperature": 0.3},
    )
    return {"content": text, "tool_calls": calls or [], "model": model}


if app is not None:
    @app.task(name="local_agent.worker_farm.tasks.distill_export", bind=True,
              autoretry_for=(OSError,), retry_backoff=True,
              retry_kwargs={"max_retries": 3})
    def distill_export(self, envelope: dict) -> dict:
        return _run_distill(envelope)

    def _maybe_followup_semantic(task, envelope: dict, mechanical: dict) -> None:
        """Enqueue the advisory semantic pass. Never fails the mechanical result."""
        from . import semantic_judge
        semantic_judge.try_enqueue_followup(
            lambda payload: judge_transcript_semantic.apply_async(
                args=[payload], queue="judge"),
            envelope, mechanical,
            str(getattr(getattr(task, "request", None), "id", "") or ""),
        )

    @app.task(name="local_agent.worker_farm.tasks.judge_transcript", bind=True,
              autoretry_for=(OSError,), retry_backoff=True,
              retry_kwargs={"max_retries": 3})
    def judge_transcript(self, envelope: dict) -> dict:
        """Deliberately simple, per the operator's own explicit decision
        (2026-09-02) to allow real chat transcripts to reach secondary
        worker machines with no filtering: this task takes the transcript
        directly in the envelope and returns findings directly as the task
        result, reusing the queue's own encryption/authentication (WireGuard
        tunnel + scoped Redis ACL) rather than adding a second
        encrypted-artifact-store layer on top, unlike distill_export above.
        That heavier pattern exists because distill_export's source data was
        never meant to leave the workstation encrypted store at all; here
        the operator already chose the opposite trust boundary. Findings are
        advisory only -- nothing here writes to memory, Chroma, or any file
        the interactive agent reads."""
        chat_id = str(envelope.get("chat_id") or "")
        messages = envelope.get("messages") or []
        if not chat_id or not isinstance(messages, list):
            raise ValueError("judge_transcript envelope needs chat_id and messages")
        mechanical = judge_rubric.summarize(chat_id, messages)
        _maybe_followup_semantic(self, envelope, mechanical)
        return mechanical

    @app.task(name="local_agent.worker_farm.tasks.judge_transcript_semantic", bind=True,
              autoretry_for=(OSError,), retry_backoff=True,
              retry_kwargs={"max_retries": 3})
    def judge_transcript_semantic(self, envelope: dict) -> dict:
        """Advisory Qwythos pass over mechanical judge_transcript output.

        Default off. Never writes chats/, learning.record, or mechanical
        status. Sidecar is farm-judge-semantic-verdict-v1.
        """
        from . import semantic_judge
        verdict = semantic_judge.judge_chat(envelope)
        if verdict is None:
            return {"skipped": True, "advisory": True, "auto_accepted": False}
        return verdict

    @app.task(name="local_agent.worker_farm.tasks.summarize_conversation", bind=True,
              autoretry_for=(OSError,), retry_backoff=True,
              retry_kwargs={"max_retries": 3})
    def summarize_conversation(self, envelope: dict) -> dict:
        """HARNESS_OPTIMIZATION.md Sec 4a: background compaction offload.
        Envelope: {"messages": [...]} -- the same message-dict shape
        context_compactor.summarize_old_messages already accepts. Advisory
        only; nothing here writes to the live conversation, memory, or any
        file the interactive agent reads. Workstation caller is
        farm_offload.try_summarize_on_farm (prefetch-only via
        compaction_prefetch / agent._maybe_start_farm_summary_prefetch)."""
        messages = envelope.get("messages") or []
        if not isinstance(messages, list) or not messages:
            raise ValueError("summarize_conversation envelope needs a non-empty messages list")
        return _summarize_messages(messages)

    @app.task(name="local_agent.worker_farm.tasks.embed_chunks", bind=True,
              autoretry_for=(OSError,), retry_backoff=True,
              retry_kwargs={"max_retries": 3})
    def embed_chunks(self, envelope: dict) -> dict:
        """HARNESS_OPTIMIZATION.md Sec 4a: background embedding offload for
        retrieval.py's EmbeddingScorer backlog. Envelope: {"chunks": [{"id":
        "...", "text": "..."}]}. Stateless -- returns vectors only, does not
        touch the on-disk embedding cache itself."""
        chunks = envelope.get("chunks") or []
        if not isinstance(chunks, list) or not chunks:
            raise ValueError("embed_chunks envelope needs a non-empty chunks list")
        return _embed_chunks(chunks)

    @app.task(name="local_agent.worker_farm.tasks.qwythos_evaluate", bind=True,
              autoretry_for=(OSError,), retry_backoff=True,
              retry_kwargs={"max_retries": 3})
    def qwythos_evaluate(self, envelope: dict) -> dict:
        """Capability routing: lightweight tool-calling on Mac Qwythos-9B.

        Shares the summarize queue (Mac concurrency=1). Caller is
        farm_offload.try_qwythos_on_farm. Advisory only — tools still execute
        on the workstation after this returns.
        """
        return _qwythos_evaluate(envelope)

    @app.task(name="local_agent.worker_farm.tasks.connectivity_probe", bind=True)
    def connectivity_probe(self) -> dict:
        """Deliberately does nothing except prove a worker on the 'probe'
        queue received a task and completed it, and that the workstation can
        read the result back. No file, no encryption, no job-registry state,
        no historical-export data -- this exists only to verify the
        WireGuard tunnel + Redis ACL credential path for a new node before
        any real preprocess/research task is written for it. See
        docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md."""
        return {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "worker_pid": os.getpid(),
            "received_at": time.time(),
        }
else:
    distill_export = None
    connectivity_probe = None
    judge_transcript = None
    judge_transcript_semantic = None
    summarize_conversation = None
    embed_chunks = None
    qwythos_evaluate = None
