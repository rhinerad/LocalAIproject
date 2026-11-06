# 2026-08-30 — run_code sandbox: pathlib bypassed the file-access guard

## What changed

`local_agent/sandbox_guard.py` monkeypatched `builtins.open`, `io.open`,
`os.open`, and `os.chdir` to refuse any path outside the sandboxed run
directory. That left a real gap: `pathlib.Path.read_text()`,
`.write_text()`, and `.open()` reach CPython's stdlib accessor, which binds
its own reference to the original `io.open` at pathlib's own import time —
before `sandbox_guard._install()` ever runs — so the monkeypatch never
intercepts it. A script running through `run_code` could read (and write)
any file the OS-level process could reach, entirely outside
`local_agent/sandbox/run_<id>/`, using nothing more exotic than
`Path(...).read_text()`.

Found while independently re-running `local_agent/test_run_code.py` for the
general-agent reprioritization: `test_script_cannot_read_project_file_outside_run_dir`
already existed and asserts exactly this contract, but failed
(`AssertionError: 0 == 0` — the read succeeded when it should have been
refused). This was a real, exploitable gap in an already-written test, not
a newly written one.

Fix: added a `sys.addaudithook` in `sandbox_guard._install()`. CPython's
C-level `io.FileIO` constructor emits an `"open"` audit event on every file
open regardless of which Python-level API reached it — `builtins.open`,
`io.open`, `os.open`, or `pathlib` — so this is the actual enforcement
boundary, immune to the attribute-caching bypass. `os.chdir` gets the same
treatment via its own `"os.chdir"` audit event. The existing monkeypatches
are kept as defense-in-depth for anything that doesn't reach the audit
system the same way.

One real complication surfaced while fixing this: the import system itself
opens `.py`/`.pyc` files through the same C-level path the audit hook
inspects, so a naive "block everything outside run_dir" audit hook also
broke ordinary `import json`/`import socket`/etc. inside the sandbox. Fixed
by allowing **read-only** opens under the interpreter's own install roots
(`sys.prefix`, `sys.exec_prefix`, `sys.base_prefix`, `sys.base_exec_prefix`)
in addition to the run directory — writes are still refused everywhere
except the run directory, and reads are still refused everywhere else
(the project tree, `outputs/equal_shares/`, arbitrary user paths).

## Why

This is a core safety boundary for the general-agent priority, not an Equal
Shares concern — `local_agent/README.md` states plainly that `run_code`
"cannot ... read [a] project file outside its run dir" and lists this as
already tested. It wasn't, for the one API (`pathlib`) a script would most
naturally reach for. Left unfixed, any model-generated script run through
`run_code` could read credentials, `.env` files, Equal Shares evidence, or
write anywhere the OS process could reach, while every existing safety
claim in the README and CLAUDE.md about the sandbox being walled to
`sandbox/run_<id>/` remained silently false for this one common code path.

## What was verified

Reproduced the bypass directly (not just via the test) before fixing:
`EQUAL_SHARES_SANDBOX_RUN=<dir> python3 -I -B sandbox_guard.py script.py`
where `script.py` did `Path(<file outside run_dir>).read_text()` — succeeded
and printed the file's contents pre-fix; refused with `PermissionError:
sandbox: path is outside the run dir: ...` post-fix, in exactly the
subprocess invocation `sandbox_runner.py` actually uses (`-I -B`, same env
vars).

```
python local_agent\test_run_code.py -v
Ran 14 tests in 2.222s
OK
```

11 pre-existing tests still pass, including the fixed
`test_script_cannot_read_project_file_outside_run_dir`. Added three new
tests: `test_script_cannot_write_outside_run_dir_via_pathlib` (the write-side
of the same bug — no prior coverage existed), `test_script_cannot_chdir_outside_run_dir`
(no prior coverage existed), and `test_ordinary_stdlib_imports_still_work_in_sandbox`
(guards against the read-root fix over-blocking legitimate imports, which it
did on the first pass before the interpreter-roots allowance was added).

Manually verified six additional scenarios beyond the test file, matching the
actual `sandbox_runner.py` invocation exactly: pathlib read escape (blocked),
plain-open read escape (still blocked, unaffected), in-sandbox pathlib
read/write (still works), ordinary multi-module stdlib imports (still work),
pathlib write escape to a fresh path (blocked, target file confirmed absent
afterward), `os.chdir` escape (blocked), and socket creation with networking
disabled (still blocked, unaffected by this change).

`python local_agent\test_native_tool_calling.py` was also re-run: 12 of 28
tests error in this sandbox on an unrelated `PermissionError` unlinking
`runtime/chat_busy.json` — a pre-existing limitation of this review
environment's mount (confirmed separately today across three other unrelated
test files; the mount cannot delete any file, including ones it just
created), not caused by this change. The specific failure signature and
count are identical before and after this edit.

## What is still unverified

This was fixed and tested only in this Linux review sandbox (Python 3.10.12,
CPython stock build). Not verified on the actual Windows workstation Python
version `run_code` runs under in production. `sys.addaudithook` and the
`"open"`/`"os.chdir"` audit events are documented CPython behavior since
3.8 (PEP 578), not platform-specific, so this should hold on Windows/any
CPython 3.8+, but that is an expectation, not a confirmed fact — worth a
quick live `run_code` smoke test on the real machine before treating this as
fully closed.
