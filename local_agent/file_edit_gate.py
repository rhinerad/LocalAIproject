"""One-shot approval for edits to executable/configuration files."""
from __future__ import annotations
import hashlib, json, threading, time, uuid
from pathlib import Path

from atomic_io import atomic_write_json

STATE_FILE = Path(__file__).resolve().parent / "runtime" / "file_edit_gate.json"
_LOCK = threading.Lock()
_LAST_GOOD: dict | None = None

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
    with _LOCK:
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
    with _LOCK:
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
