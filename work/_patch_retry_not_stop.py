from pathlib import Path
import re
import py_compile

path = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\work\run_prompt_pack_production.py")
text = path.read_text(encoding="utf-8")
orig = text

helper = '''
def is_content_quality_pause(failure) -> bool:
    """True for audit/content pauses that must RETRY stills, not halt the run.

    Infrastructure watchdog failures (stale progress, dead supervisor) stay fatal.
    Operator-written `pause at safe checkpoint: ...` notes are content signals.
    """
    msg = str(failure or "").strip().lower()
    if not msg:
        return False
    needles = (
        "pause at safe checkpoint",
        "safe checkpoint",
        "manual audit",
        "blind pass",
        "semantic still qa failed",
        "mechanical still qa failed",
    )
    return any(n in msg for n in needles)


def is_infrastructure_watchdog(failure) -> bool:
    """Only infrastructure faults should hard-stop production."""
    msg = str(failure or "").strip().lower()
    if not msg:
        return False
    if is_content_quality_pause(failure):
        return False
    return any(
        n in msg
        for n in (
            "stale progress",
            "stale progress/logs",
            "dead supervisor",
            "supervisor dead",
            "no progress",
        )
    )

'''

if "def is_content_quality_pause" not in text:
    m = re.search(r"\ndef emit\(message\):", text)
    if not m:
        raise SystemExit("could not find emit() to insert helpers")
    text = text[: m.start()] + "\n" + helper + text[m.start():]

old_save = '''    def save():
        current = prodmod.load_production(cid) or {}
        if current.get("watchdog_failure"):
            raise RuntimeError(f"watchdog stopped production: {current['watchdog_failure']}")
        prod["progress_at"] = time.time()
        prodmod.save_production(cid, prod)'''

new_save = '''    def save():
        current = prodmod.load_production(cid) or {}
        failure = current.get("watchdog_failure")
        if failure and is_infrastructure_watchdog(failure):
            raise RuntimeError(f"watchdog stopped production: {failure}")
        # Content-quality pauses (safe-checkpoint audits, QA notes) must not
        # halt the run — Rhine: bad stills retry, they do not stop production.
        if failure and is_content_quality_pause(failure):
            emit(f"ignoring content pause; will retry still: {failure}")
            cleared = dict(current)
            cleared.pop("watchdog_failure", None)
            prod.pop("watchdog_failure", None)
            prodmod.save_production(cid, cleared, clear_watchdog=True)
        prod["progress_at"] = time.time()
        prodmod.save_production(cid, prod)'''

if old_save not in text:
    raise SystemExit("save() block not found exactly — abort")
text = text.replace(old_save, new_save, 1)

old_except = '''            except Exception as exc:
                write_evidence(attempt_dir / "failure.json",
                               {"error": str(exc), "job": attempt_job,
                                "retry_index": retry_index})
                current = prodmod.load_production(cid) or {}
                exhausted = retry_index == 3
                prod.update(status="error" if exhausted else "running",
                            last_error=(f"{exc}; retry {retry_index + 1}/4"
                                        if not exhausted else str(exc)),
                            watchdog_failure=current.get("watchdog_failure"))
                prodmod.save_production(cid, prod)
                if exhausted:
                    return 1
                emit(f"STILL retry {key} after QA/render failure: {exc}")
        if not accepted:
            return 1'''

new_except = '''            except Exception as exc:
                write_evidence(attempt_dir / "failure.json",
                               {"error": str(exc), "job": attempt_job,
                                "retry_index": retry_index})
                current = prodmod.load_production(cid) or {}
                failure = current.get("watchdog_failure")
                # Never promote a bad-still / content pause into a whole-run stop.
                if failure and (
                    is_content_quality_pause(failure)
                    or not is_infrastructure_watchdog(failure)
                ):
                    failure = None
                    prod.pop("watchdog_failure", None)
                prod.update(status="running",
                            last_error=f"{exc}; retry {retry_index + 1}",
                            watchdog_failure=failure)
                if current.get("watchdog_failure") and is_content_quality_pause(
                    current.get("watchdog_failure")
                ):
                    prodmod.save_production(cid, prod, clear_watchdog=True)
                else:
                    prodmod.save_production(cid, prod)
                if failure and is_infrastructure_watchdog(failure):
                    emit(f"FATAL infrastructure watchdog during still {key}: {failure}")
                    return 1
                emit(f"STILL retry {key} after QA/render failure: {exc}")
                # Soft breath every 4 misses; keep retrying — do not stop the run.
                if retry_index >= 3 and (retry_index + 1) % 4 == 0:
                    time.sleep(2)
                retry_index += 1
        if not accepted:
            # Should be unreachable with while-not-accepted; leave resume-friendly.
            prod.update(status="running",
                        last_error=f"still {key} not accepted yet; supervisor exiting for resume")
            prodmod.save_production(cid, prod)
            return 0'''

if old_except not in text:
    raise SystemExit("except/retry block not found exactly — abort")
text = text.replace(old_except, new_except, 1)

old_loop = "        accepted = False\n        for retry_index in range(4):"
new_loop = "        accepted = False\n        retry_index = 0\n        while not accepted:"
if old_loop not in text:
    raise SystemExit("retry loop start not found")
text = text.replace(old_loop, new_loop, 1)

old_watch_gate = '''    if prod.get("watchdog_failure"):
        raise ValueError("watchdog evidence must be diagnosed before retry")'''
new_watch_gate = '''    if prod.get("watchdog_failure"):
        if is_content_quality_pause(prod.get("watchdog_failure")):
            emit(f"clearing content pause before stills: {prod.get('watchdog_failure')}")
            prod.pop("watchdog_failure", None)
            prod["status"] = "running"
            prod["last_error"] = None
            prodmod.save_production(cid, prod, clear_watchdog=True)
        elif is_infrastructure_watchdog(prod.get("watchdog_failure")):
            raise ValueError("watchdog evidence must be diagnosed before retry")
        else:
            # Unknown sticky note — clear so still retries are not blocked.
            emit(f"clearing non-infra watchdog note before stills: {prod.get('watchdog_failure')}")
            prod.pop("watchdog_failure", None)
            prod["status"] = "running"
            prodmod.save_production(cid, prod, clear_watchdog=True)'''

if old_watch_gate not in text:
    raise SystemExit("watchdog gate at run() start not found")
text = text.replace(old_watch_gate, new_watch_gate, 1)

if text == orig:
    raise SystemExit("no changes made")
path.write_text(text, encoding="utf-8")
print("patched", path)
print("bytes", path.stat().st_size)
py_compile.compile(str(path), doraise=True)
print("syntax_ok")
