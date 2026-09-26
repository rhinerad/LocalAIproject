"""The scheduler was orphaned: created but never callable and never delivered.

These tests pin both connections — the phone can create a schedule, and the
bridge actually sends the due messages back.
"""
import json, sys, tempfile, threading, types, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import phone_scheduler, remote_security, tools

PHONE = "a" * 32
OTHER = "b" * 32


def phone_ctx(identity=PHONE):
    return remote_security.ToolContext(source="phone", remote_identity=identity,
                                       allowed_tools=frozenset())


class Registration(unittest.TestCase):
    def test_registered_with_schemas(self):
        for name in ("schedule_phone_messages", "list_phone_schedules",
                     "cancel_phone_schedule"):
            self.assertIn(name, tools.TOOLS)
            self.assertIn(name, tools._SCHEMAS)

    def test_schema_has_no_recipient_field(self):
        # The model must not be able to name a target at all.
        props = tools._SCHEMAS["schedule_phone_messages"]["properties"]
        for banned in ("identity", "recipient", "to", "target", "address"):
            self.assertNotIn(banned, props)


class SourceBinding(unittest.TestCase):
    def setUp(self):
        # A temp dir, never the project's runtime folder: a test must not be able
        # to disturb a real pending schedule.
        self._tmp = tempfile.TemporaryDirectory()
        self.state = Path(self._tmp.name) / "sched.json"
        self._orig = (phone_scheduler.STATE, phone_scheduler.AUDIT)
        phone_scheduler.STATE = self.state
        phone_scheduler.AUDIT = Path(self._tmp.name) / "audit.jsonl"

    def tearDown(self):
        phone_scheduler.STATE, phone_scheduler.AUDIT = self._orig
        self._tmp.cleanup()

    def test_desktop_is_refused(self):
        out = tools.call("schedule_phone_messages",
                         {"message": "count {n}", "interval_seconds": 30, "count": 3})
        self.assertTrue(out.startswith("ERROR"))
        self.assertIn("phone-only", out)

    def test_model_cannot_forge_an_identity(self):
        # A model-supplied identity must be stripped by the dispatch seam.
        out = tools.call("schedule_phone_messages",
                         {"message": "x", "interval_seconds": 30, "count": 1,
                          "__remote_schedule_identity": OTHER})
        self.assertTrue(out.startswith("ERROR"), out)

    def test_phone_call_binds_to_the_caller(self):
        out = tools.call("schedule_phone_messages",
                         {"message": "count {n}", "interval_seconds": 30, "count": 3},
                         context=phone_ctx())
        self.assertFalse(out.startswith("ERROR"), out)
        self.assertIn("scheduled", json.loads(out))

    def test_counter_only_phone_request_defaults_to_counter_template(self):
        out = tools.call("schedule_phone_messages",
                         {"interval_seconds": 30, "count": 3, "start": 4},
                         context=phone_ctx())
        self.assertFalse(out.startswith("ERROR"), out)
        self.assertEqual(
            next(iter(phone_scheduler._load(self.state)["jobs"].values()))["template"],
            "{n}")


class Dispatch(unittest.TestCase):
    """The half that was missing entirely: something must actually send."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state = Path(self._tmp.name) / "dispatch.json"
        self._orig = (phone_scheduler.STATE, phone_scheduler.AUDIT)
        # Dispatch tests must never create fixtures in the live phone queue.
        phone_scheduler.STATE = self.state
        phone_scheduler.AUDIT = Path(self._tmp.name) / "audit.jsonl"

    def tearDown(self):
        phone_scheduler.STATE, phone_scheduler.AUDIT = self._orig
        self._tmp.cleanup()

    def test_counts_up_at_the_interval(self):
        t0 = 1000.0
        phone_scheduler.create(PHONE, "count {n}", 30, 4, start=0,
                               now=t0, path=self.state)
        sent = []
        send = lambda ident, msg, meta: sent.append((ident, msg))

        phone_scheduler.dispatch_due(send, now=t0, path=self.state)
        self.assertEqual([m for _, m in sent], ["count 0"])

        # not due one second later
        phone_scheduler.dispatch_due(send, now=t0 + 1, path=self.state)
        self.assertEqual(len(sent), 1)

        for i in range(1, 4):
            phone_scheduler.dispatch_due(send, now=t0 + 30 * i, path=self.state)
        self.assertEqual([m for _, m in sent],
                         ["count 0", "count 1", "count 2", "count 3"])
        self.assertTrue(all(i == PHONE for i, _ in sent))

        # completed — no fifth message
        phone_scheduler.dispatch_due(send, now=t0 + 300, path=self.state)
        self.assertEqual(len(sent), 4)

    def test_audit_records_the_counter_that_was_queued(self):
        t0 = 1500.0
        phone_scheduler.create(PHONE, "{n}", 30, 2, start=4, now=t0,
                               path=self.state)
        phone_scheduler.dispatch_due(lambda *_: None, now=t0, path=self.state)
        record = json.loads(phone_scheduler.AUDIT.read_text(encoding="utf8").splitlines()[-1])
        self.assertEqual(record["event"], "queued")
        self.assertEqual(record["counter"], 4)

    def test_unpairing_blocks_rather_than_looping(self):
        t0 = 2000.0
        phone_scheduler.create(PHONE, "x", 30, 5, now=t0, path=self.state)

        def refuse(ident, msg, meta):
            raise phone_scheduler.ScheduleBlocked("unpaired")

        phone_scheduler.dispatch_due(refuse, now=t0, path=self.state)
        jobs = phone_scheduler.list_for_identity(PHONE, path=self.state)
        self.assertEqual(jobs[0]["status"], "blocked")

    def test_transient_failure_is_not_counted_as_sent(self):
        t0 = 3000.0
        phone_scheduler.create(PHONE, "x", 30, 5, now=t0, path=self.state)

        def boom(ident, msg, meta):
            raise RuntimeError("radio down")

        phone_scheduler.dispatch_due(boom, now=t0, path=self.state)
        job = phone_scheduler.list_for_identity(PHONE, path=self.state)[0]
        self.assertEqual(job["queued_count"], 0)
        self.assertEqual(job["status"], "active")

    def test_concurrent_dispatchers_claim_one_message_once(self):
        """A durable lease must stop a second bridge loop duplicating a send."""
        t0 = 4000.0
        phone_scheduler.create(PHONE, "count {n}", 30, 2, now=t0, path=self.state)
        entered, release, sent = threading.Event(), threading.Event(), []

        def slow_send(ident, message, meta):
            sent.append(message)
            entered.set()
            release.wait(timeout=2)

        first = threading.Thread(
            target=phone_scheduler.dispatch_due, args=(slow_send,),
            kwargs={"now": t0, "path": self.state}, daemon=True)
        first.start()
        self.assertTrue(entered.wait(timeout=1))
        self.assertEqual(phone_scheduler.dispatch_due(slow_send, now=t0, path=self.state), [])
        release.set()
        first.join(timeout=2)
        self.assertEqual(sent, ["count 0"])
        self.assertEqual(phone_scheduler.list_for_identity(PHONE, path=self.state)[0]["queued_count"], 1)

    def test_expired_lease_is_not_retried_blindly(self):
        t0 = 5000.0
        job = phone_scheduler.create(PHONE, "count {n}", 30, 2, now=t0, path=self.state)
        raw = phone_scheduler._load(self.state)
        raw["jobs"][job["id"]]["dispatch_lease"] = {
            "id": "crashed", "counter": 0, "claimed_at": t0,
            "expires_at": t0 + 1,
        }
        phone_scheduler._save(raw, self.state)
        sent = []
        self.assertEqual(phone_scheduler.dispatch_due(
            lambda *args: sent.append(args), now=t0 + 2, path=self.state), [])
        actual = phone_scheduler.list_for_identity(PHONE, path=self.state)[0]
        self.assertEqual(sent, [])
        self.assertEqual(actual["status"], "uncertain")


def _import_bridge():
    """Import lxmf_agent, stubbing optional heavy deps that may be absent.

    The bridge transitively imports the whole agent stack (chromadb and friends).
    Those are irrelevant to scheduling, so a missing optional dependency must not
    hide a real wiring regression.
    """
    import importlib

    class _Any(types.ModuleType):
        """Stub that satisfies both `import x` and `from x import Name`."""
        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return _Any(name)

    for _ in range(20):
        try:
            return importlib.import_module("lxmf_agent")
        except (ModuleNotFoundError, ImportError) as exc:
            missing = getattr(exc, "name", None) or ""
            if not missing or missing.startswith(("lxmf_agent", "phone_scheduler")):
                raise
            root = missing.split(".")[0]
            for mod in (root, missing):
                sys.modules.setdefault(mod, _Any(mod))
                sys.modules[mod] = _Any(mod)
    raise unittest.SkipTest("too many missing optional dependencies")


class BridgeWiring(unittest.TestCase):
    """The bridge must call the scheduler — this is what was never connected."""

    def test_loop_drains_and_reply_path_is_used(self):
        lxmf_agent = _import_bridge()
        src = Path(lxmf_agent.__file__).read_text(encoding="utf8")
        self.assertIn("self.core.drain_scheduled()", src, "run loop never drains")
        self.assertIn("phone_scheduler.dispatch_due", src)

        bridge = lxmf_agent.BridgeCore.__new__(lxmf_agent.BridgeCore)
        replies = []
        bridge._reply = lambda sh, text, rid, cid="", kind="": replies.append((sh, text, kind))
        bridge.security = types.SimpleNamespace(
            get_pair=lambda i, p=None: {"active": True, "conversation_id": "c1"})
        bridge.pairings_path = None
        bridge._scheduled_send(PHONE, "count 7", {"job_id": "j1"})
        self.assertEqual(replies[0][1], "count 7")
        self.assertEqual(replies[0][2], "scheduled")
        self.assertEqual(replies[0][0], bytes.fromhex(PHONE))

    def test_unpaired_identity_raises_blocked(self):
        lxmf_agent = _import_bridge()
        bridge = lxmf_agent.BridgeCore.__new__(lxmf_agent.BridgeCore)
        bridge.security = types.SimpleNamespace(get_pair=lambda i, p=None: None)
        bridge.pairings_path = None
        with self.assertRaises(phone_scheduler.ScheduleBlocked):
            bridge._scheduled_send(PHONE, "x", {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
