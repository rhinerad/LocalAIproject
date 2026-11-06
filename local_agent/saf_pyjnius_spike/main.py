#!/usr/bin/env python3
"""Minimal p4a/pyjnius SAF tree-grant spike (companion PR 3b).

Not the daily-driver companion. Package local.equalshares.safspike.
Requests ACTION_OPEN_DOCUMENT_TREE, takes a *read-only* persistable URI
permission, and dumps ContentResolver.getPersistedUriPermissions() on
start so a later run can show whether the grant survived process death.

Does not walk file:// paths, does not call pm, does not install anything.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

__version__ = "0.0.1"

REQUEST_TREE = 0x5AF1
LOG_NAME = "saf_spike_log.jsonl"
GRANT_NAME = "saf_spike_grants.json"


def _now() -> float:
    return time.time()


def append_log(row: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def load_grants(dest: Path) -> list[dict]:
    if not dest.is_file():
        return []
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    if isinstance(data, list):
        return data
    return []


def save_grants(rows: list[dict], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def record_grant(tree_uri: str, dest: Path) -> dict:
    rows = load_grants(dest)
    row = {
        "tree_uri": tree_uri,
        "flags": ["read"],
        "granted_at": _now(),
    }
    rows = [r for r in rows if r.get("tree_uri") != tree_uri]
    rows.append(row)
    save_grants(rows, dest)
    return row


def is_android() -> bool:
    try:
        from android import mActivity  # noqa: F401
        return True
    except Exception:
        return False


def persisted_uri_rows() -> list[dict]:
    """Live ContentResolver persisted URI permissions. Empty off-device."""
    if not is_android():
        return []
    from android import mActivity
    resolver = mActivity.getContentResolver()
    perms = resolver.getPersistedUriPermissions()
    rows: list[dict] = []
    n = int(perms.size())
    for i in range(n):
        item = perms.get(i)
        uri = item.getUri()
        rows.append({
            "tree_uri": str(uri.toString()) if uri is not None else "",
            "is_read": bool(item.isReadPermission()),
            "is_write": bool(item.isWritePermission()),
        })
    return rows


def open_document_tree() -> str:
    """Launch the system tree picker. Returns a status string."""
    if not is_android():
        return "desktop: no-op (spike requires p4a)"
    from android import mActivity
    from jnius import autoclass
    Intent = autoclass("android.content.Intent")
    intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    intent.addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
    mActivity.startActivityForResult(intent, REQUEST_TREE)
    return "picker-launched"


def take_read_persistable(intent) -> str | None:
    """takePersistableUriPermission with READ only. Returns URI or None."""
    if intent is None:
        return None
    from android import mActivity
    from jnius import autoclass
    Activity = autoclass("android.app.Activity")
    Intent = autoclass("android.content.Intent")
    uri = intent.getData()
    if uri is None:
        return None
    flags = int(intent.getFlags())
    read_only = flags & int(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    if read_only == 0:
        read_only = int(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    mActivity.getContentResolver().takePersistableUriPermission(uri, read_only)
    return str(uri.toString())


class SafSpikeApp:
    """UI wrapper. Instantiated from main() so tests can import helpers."""

    def __init__(self) -> None:
        self.status = "idle"
        self.log_path = Path(LOG_NAME)
        self.grant_path = Path(GRANT_NAME)
        self._label = None

    def files_dir(self) -> Path:
        if is_android():
            from android import mActivity
            return Path(str(mActivity.getFilesDir().getAbsolutePath()))
        return Path(".")

    def bind_activity(self) -> None:
        if not is_android():
            return
        from android import activity
        activity.bind(on_activity_result=self._on_activity_result)

    def _on_activity_result(self, request_code, result_code, data) -> None:
        from jnius import autoclass
        Activity = autoclass("android.app.Activity")
        if int(request_code) != REQUEST_TREE:
            return
        if int(result_code) != int(Activity.RESULT_OK):
            self._note("picker-cancelled")
            return
        uri = take_read_persistable(data)
        if not uri:
            self._note("no-uri")
            return
        record_grant(uri, self.files_dir() / GRANT_NAME)
        self._note("persisted", extra={"tree_uri": uri,
                                       "persisted": persisted_uri_rows()})

    def _note(self, event: str, extra: dict | None = None) -> None:
        row = {"at": _now(), "event": event}
        if extra:
            row.update(extra)
        append_log(row, self.files_dir() / LOG_NAME)
        self.status = event
        if self._label is not None:
            self._label.text = self._format_status()

    def _format_status(self) -> str:
        persisted = persisted_uri_rows()
        grants = load_grants(self.files_dir() / GRANT_NAME)
        lines = [
            f"status: {self.status}",
            f"local grant rows: {len(grants)}",
            f"OS persisted URIs: {len(persisted)}",
            "grantable trees only (Documents/...), not Download or volume root",
            "read-only takePersistableUriPermission",
        ]
        for item in persisted:
            lines.append(
                f"- read={item['is_read']} write={item['is_write']} "
                f"{item['tree_uri']}"
            )
        return "\n".join(lines)

    def build(self):
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.scrollview import ScrollView

        self.log_path = self.files_dir() / LOG_NAME
        self.grant_path = self.files_dir() / GRANT_NAME
        root = BoxLayout(orientation="vertical", padding=16, spacing=12)
        btn = Button(text="Grant a folder (SAF tree)", size_hint=(1, 0.2))
        btn.bind(on_press=lambda *_: self._launch())
        self._label = Label(
            text=self._format_status(),
            size_hint=(1, None),
            halign="left",
            valign="top",
        )
        self._label.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
        self._label.bind(texture_size=lambda inst, ts: setattr(inst, "height", ts[1]))
        scroll = ScrollView(size_hint=(1, 0.8))
        scroll.add_widget(self._label)
        root.add_widget(btn)
        root.add_widget(scroll)
        return root

    def _launch(self) -> None:
        msg = open_document_tree()
        self._note(msg)

    def on_start(self) -> None:
        self.bind_activity()
        self._note("on_start", extra={"persisted": persisted_uri_rows()})


def main() -> None:
    from kivy.app import App

    spike = SafSpikeApp()

    class _App(App):
        def build(self):
            return spike.build()

        def on_start(self):
            spike.on_start()

    _App().run()


if __name__ == "__main__":
    main()
