"""Broker-URL credential redaction is scheme-agnostic (audit 2026-11-02 #6).

The three redactors (farm_core.sanitize_text, farm_health._redact,
dashboard.collect.redact_secrets) must mask the exact URL shape the Mac worker
uses -- redis://<user>:<urlsafe-b64>@10.90.90.1:6379/0 -- as well as the
password-only form, rediss://, and other schemes with a userinfo part.

Correct invocation -- from the repository root:

  python -m pytest -p no:cacheprovider -q local_agent/worker_farm/test_redaction.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from local_agent.worker_farm import farm_core, farm_health  # noqa: E402
from local_agent.worker_farm.dashboard import collect  # noqa: E402

# Exactly the shape Add-Phase1SecondaryWorkerCredential.ps1 writes for the Mac:
# username, 48-char URL-safe base64 password, tunnel hub, port, db 0.
MAC_PASSWORD = "Qm9ndXMtcGFzc3dvcmQtbm90LXJlYWwtZm9yLXRlc3Rpbmctb25seQ"
MAC_URL = f"redis://mac_worker:{MAC_PASSWORD}@10.90.90.1:6379/0"
LOOPBACK_URL = "redis://:super-secret-pass@127.0.0.1:6379/0"
TLS_URL = f"rediss://mac_worker:{MAC_PASSWORD}@10.90.90.1:6380/0"
AMQP_URL = "amqp://guest:guestpw@rabbit.local:5672/vhost"
HTTPS_URL = "https://alice:hunter2@example.com/path"
NO_CREDS = "redis://10.90.90.1:6379/0"


class _Shared:
    def redact(self, text: str) -> str:
        raise NotImplementedError

    def test_mac_worker_url_password_is_masked(self):
        out = self.redact(f"kombu failed: {MAC_URL}")
        self.assertNotIn(MAC_PASSWORD, out)
        self.assertIn("@10.90.90.1:6379/0", out)

    def test_password_only_loopback_url_is_masked(self):
        out = self.redact(LOOPBACK_URL)
        self.assertNotIn("super-secret-pass", out)
        self.assertIn("@127.0.0.1:6379/0", out)

    def test_rediss_scheme_is_masked(self):
        out = self.redact(TLS_URL)
        self.assertNotIn(MAC_PASSWORD, out)
        self.assertTrue(out.lower().startswith("rediss://"))

    def test_other_schemes_with_userinfo_are_masked(self):
        for url, secret in ((AMQP_URL, "guestpw"), (HTTPS_URL, "hunter2")):
            with self.subTest(url=url):
                self.assertNotIn(secret, self.redact(url))

    def test_url_without_credentials_is_unchanged(self):
        self.assertEqual(NO_CREDS, self.redact(NO_CREDS))

    def test_mixed_case_scheme_and_embedded_in_json(self):
        blob = '{"broker": "REDIS://mac_worker:' + MAC_PASSWORD + '@10.90.90.1:6379/0"}'
        self.assertNotIn(MAC_PASSWORD, self.redact(blob))

    def test_two_urls_in_one_line_both_masked(self):
        out = self.redact(f"{MAC_URL} then {LOOPBACK_URL}")
        self.assertNotIn(MAC_PASSWORD, out)
        self.assertNotIn("super-secret-pass", out)


class FarmHealthRedactTests(_Shared, unittest.TestCase):
    def redact(self, text):
        return farm_health._redact(text)

    def test_existing_marker_shape_is_kept(self):
        self.assertIn("redis://:***@", farm_health._redact(LOOPBACK_URL))

    def test_username_is_kept_for_diagnosis(self):
        self.assertIn("redis://mac_worker:***@", farm_health._redact(MAC_URL))


class DashboardRedactTests(_Shared, unittest.TestCase):
    def redact(self, text):
        return collect.redact_secrets(text) or ""

    def test_none_passes_through(self):
        self.assertIsNone(collect.redact_secrets(None))

    def test_marker_shape(self):
        self.assertIn("redis://mac_worker:***@", collect.redact_secrets(MAC_URL))
        self.assertIn("redis://:***@", collect.redact_secrets(LOOPBACK_URL))


class FarmCoreSanitizeTests(_Shared, unittest.TestCase):
    def redact(self, text):
        return farm_core.sanitize_text(text)

    def test_regex_is_scheme_agnostic(self):
        self.assertEqual(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@]*@",
                         farm_core._URL_CREDENTIAL_RE.pattern)

    def test_sanitize_replaces_whole_userinfo(self):
        out = farm_core.sanitize_text(MAC_URL)
        self.assertIn("redis://<REDACTED>@10.90.90.1:6379/0", out)


if __name__ == "__main__":
    unittest.main()
