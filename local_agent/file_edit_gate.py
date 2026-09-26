"""One-shot approval for edits to executable/configuration files."""
from __future__ import annotations
import hashlib, json, threading, time, uuid
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent / "runtime" / "file_edit_gate.json"
_LOCK = threading.Lock()

def _load():
    try:
        d=json.loads(STATE_FILE.read_text(encoding="utf-8")); d.setdefault("pending",[]); d.setdefault("approved",[]); return d
    except Exception: return {"pending":[],"approved":[],"history":[]}
def _save(d):
    STATE_FILE.parent.mkdir(parents=True,exist_ok=True); d["updated_at"]=time.time(); t=STATE_FILE.with_suffix('.tmp'); t.write_text(json.dumps(d,indent=2),encoding="utf-8"); t.replace(STATE_FILE)
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
    with _LOCK: d=_load(); _save(d); return d
