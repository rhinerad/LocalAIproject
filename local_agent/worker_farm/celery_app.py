"""Celery configuration; importing this module never starts a broker or worker."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

try:
    from celery import Celery
    from kombu import Exchange, Queue as KombuQueue
except ImportError as exc:  # importable diagnostics before optional installation
    Celery = None
    CELERY_IMPORT_ERROR = exc
else:
    CELERY_IMPORT_ERROR = None


# The one WireGuard tunnel-hub address a secondary node's Celery client is
# permitted to target (see docs/WORKER_FARM_PHASE1_5_SECONDARY_NODE_PLAN_2026-08-29.md
# and docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md). This is deliberately
# a single fixed address, not "any private IP" -- it is reachable only through
# a point-to-point/hub WireGuard tunnel that never touches the open LAN, and
# every connection through it still requires its own scoped Redis ACL
# credential (Add-Phase1SecondaryWorkerCredential.ps1). Widening this from
# 127.0.0.1-only was intentionally deferred until a secondary node was
# actually being implemented, per that plan doc's own note; that is now.
FARM_TUNNEL_HUB_HOST = "10.90.90.1"
_ALLOWED_REDIS_HOSTS = {"127.0.0.1", FARM_TUNNEL_HUB_HOST}


def _is_authenticated_loopback_redis_url(value: str) -> bool:
    """Phase 1 accepts only the workstation loopback or the one tunnel-hub
    address above -- never an arbitrary remote/private host."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "redis"
        and parsed.hostname in _ALLOWED_REDIS_HOSTS
        and port == 6379
        and bool(parsed.password)
        and not parsed.query
        and parsed.path in {"/0", "/1"}
    )


def create_app():
    if Celery is None:
        raise RuntimeError("Celery is not installed. Install local_agent/worker_farm/requirements.txt") from CELERY_IMPORT_ERROR
    broker = os.environ.get("FARM_BROKER_URL", "")
    backend = os.environ.get("FARM_RESULT_BACKEND", broker)
    if not _is_authenticated_loopback_redis_url(broker):
        raise RuntimeError("FARM_BROKER_URL must be an authenticated 127.0.0.1 Redis URL")
    if not _is_authenticated_loopback_redis_url(backend):
        raise RuntimeError("FARM_RESULT_BACKEND must be an authenticated 127.0.0.1 Redis URL")
    app = Celery("local_agent_worker_farm", broker=broker,
                 backend=backend,
                 include=["local_agent.worker_farm.tasks"])
    # Explicit queue declarations with the default (empty-string) direct exchange
    # so both submitters and workers agree on the Redis list key. Without this,
    # Kombu defaults to a named exchange matching the queue name, making the
    # worker BLPOP from "probeprobe" while submitters write to "probe".
    _default_exchange = Exchange("", type="direct")
    # NOTE, 2026-09-02: the `judge` queue was originally added to task_routes
    # only, not task_queues -- Kombu silently created a mismatched exchange
    # for it and jobs never reached a real worker until that was caught and
    # fixed (see CHANGELOG/2026-09-02b_...). Every queue below is added to
    # BOTH dicts for exactly that reason; do not add one without the other.
    _queues = [
        KombuQueue("distill",   exchange=_default_exchange, routing_key="distill"),
        KombuQueue("probe",     exchange=_default_exchange, routing_key="probe"),
        KombuQueue("judge",     exchange=_default_exchange, routing_key="judge"),
        KombuQueue("summarize", exchange=_default_exchange, routing_key="summarize"),
        KombuQueue("embed",     exchange=_default_exchange, routing_key="embed"),
    ]
    app.conf.update(
        task_serializer="json", result_serializer="json", accept_content=["json"],
        task_acks_late=True, task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1, task_track_started=True,
        broker_transport_options={"visibility_timeout": 3600},
        task_queues=_queues,
        task_routes={
            "local_agent.worker_farm.tasks.distill_export": {"queue": "distill"},
            "local_agent.worker_farm.tasks.connectivity_probe": {"queue": "probe"},
            "local_agent.worker_farm.tasks.judge_transcript": {"queue": "judge"},
            "local_agent.worker_farm.tasks.judge_transcript_semantic": {"queue": "judge"},
            "local_agent.worker_farm.tasks.summarize_conversation": {"queue": "summarize"},
            "local_agent.worker_farm.tasks.qwythos_evaluate": {"queue": "summarize"},
            "local_agent.worker_farm.tasks.embed_chunks": {"queue": "embed"},
        },
        timezone="America/New_York", enable_utc=True,
    )
    return app


app = create_app() if Celery is not None and os.environ.get("FARM_BROKER_URL") else None
