"""One-shot approval for edits to executable/configuration files."""
from __future__ import annotations
import contextlib, hashlib, json, os, threading, time, uuid
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from atomic_io import atomic_write_json

STATE_FILE = Path(__file__).resolve().parent / "runtime" / "file_edit_gate.json"
_LOCK = threading.Lock()
_LAST_GOOD: dict | None = None

LOCK_TIMEOUT_SECONDS = 10.0

@contextlib.contextmanager
def _file_lock():
    """Cross-process exclusive lock held across one load+save.

    The GUI server and the LXMF bridge are separate processes; without this a
    concurrent request()/decide() pair could lose an approval or let one
    one-shot approval be consumed twice (AUDIT_2026-11-02 finding 11).
    Same mechanism as gpu_gate._file_lock.
    """
    path = STATE_FILE.with_name(STATE_FILE.name + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                if os.name == "nt":
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"file_edit_gate lock {path} held for more than "
                                       f"{LOCK_TIMEOUT_SECONDS:.0f}s") from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                if os.name == "nt":
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(fd)

def _blank(): return {"pending":[],"approved":[],"history":[]}
def _load():
    """Blank only when the file is missing or not valid JSON; any other OSError propagates."""
    global _LAST_GOOD
    try: text=STATE_FILE.read_text(encoding="utf-8")
    except FileNotFoundError: return _blank()
    try: d=json.loads(text)
    except ValueError: return _blank()
    if not isinstance(d, dict): return _blank()
    d.setdefault("pending",[]); d.setdefault("approved",[]); d.setdefault("history",[])
    _LAST_GOOD=json.loads(json.dumps(d)); return d
def _save(d):
    global _LAST_GOOD
    d["updated_at"]=time.time(); atomic_write_json(STATE_FILE, d); _LAST_GOOD=json.loads(json.dumps(d))
def key(path, content): return hashlib.sha256((str(path)+"\0"+str(content)).encode("utf-8")).hexdigest()
def request(path, content, metadata=None, *, consume=True):
    """Request one exact edit approval.

    ``consume=False`` is intentionally a read-only reservation check for the
    loop-engineering controller.  It lets that controller surface an existing
    approval without spending it; only the normal write path may consume a
    one-shot approval and change a file.
    """
    k=key(path,content)
    with _LOCK, _file_lock():
        d=_load()
        if k in d["approved"]:
            if consume:
                d["approved"].remove(k); _save(d)
            return {"granted":True, "approval_available":not consume, "key":k}
        for x in d["pending"]:
            if x["key"]==k: return {"granted":False,"request":x}
        x={"id":"edit_"+uuid.uuid4().hex[:12],"path":str(path),"content_sha256":hashlib.sha256(str(content).encode()).hexdigest(),"chars":len(str(content)),"key":k,"created_at":time.time()}
        if isinstance(metadata, dict): x["metadata"]={str(k):str(v)[:500] for k,v in metadata.items()}
        d["pending"].append(x); _save(d); return {"granted":False,"request":x, "key":k}
def decide(request_id, approve):
    with _LOCK, _file_lock():
        d=_load(); x=next((v for v in d["pending"] if v["id"]==str(request_id)),None)
        if not x: raise ValueError("file-edit permission request was not found")
        d["pending"]=[v for v in d["pending"] if v is not x]; x["decision"]="approved" if approve else "denied"; x["decided_at"]=time.time()
        if approve: d["approved"].append(x["key"])
        d.setdefault("history",[]); d["history"]=[x]+d["history"][:29]; _save(d); return x
def snapshot():
    """Read-only. Never writes; a transient read error returns the last good state."""
    with _LOCK:
        try: return _load()
        except OSError:
            d=json.loads(json.dumps(_LAST_GOOD)) if _LAST_GOOD else _blank(); d["stale"]=True; return d
