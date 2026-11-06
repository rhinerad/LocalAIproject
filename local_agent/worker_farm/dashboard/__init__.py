"""Stdlib farm-status dashboard (loopback HTTP on :8765; LAN opt-in).

Polls existing farm_status.json / farm_health CLI / service checks.
Does not reimplement Celery or Redis probes.
"""
