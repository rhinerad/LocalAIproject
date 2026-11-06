"""Local CA + server/device certificates for G2 mTLS. Workstation files only."""
from __future__ import annotations

import getpass
import hashlib
import ipaddress
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .constants import MAX_DEVICE_ID_CHARS, PHONE_BIND_HOST

_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,%d}$" % MAX_DEVICE_ID_CHARS)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── secret-file lockdown ─────────────────────────────────────────────────
#
# Same policy as the farm Lock-Phase1SecretFile.ps1 helper: inheritance off,
# then only NT AUTHORITY\SYSTEM and the account running this process get
# (R,W). BUILTIN\Administrators is deliberately NOT granted (that group holds
# other interactive users on this workstation). On POSIX the file is 0600.
# The user is derived at runtime, never hard-coded.

SECRET_ACL_SYSTEM = "NT AUTHORITY\\SYSTEM"
SECRET_ACL_RIGHTS = "(R,W)"


def current_user_account(platform: str = sys.platform, *, run=subprocess.run) -> str:
    """DOMAIN\\user on Windows (whoami), the login name elsewhere; '' if unknown."""
    if platform == "win32":
        try:
            who = run(["whoami"], capture_output=True, text=True, check=False, timeout=10)
            name = (getattr(who, "stdout", "") or "").strip()
            if name:
                return name
        except (OSError, subprocess.SubprocessError):
            pass
        user = os.environ.get("USERNAME", "").strip()
        domain = os.environ.get("USERDOMAIN", "").strip()
        if user:
            return f"{domain}\\{user}" if domain else user
    try:
        return getpass.getuser()
    except Exception:
        return ""


def secret_acl_argv(path: Path | str, user: str) -> list[str]:
    """icacls argv granting SYSTEM + user (R,W) only, inheritance removed."""
    if not user or "\n" in user or "\r" in user:
        raise ValueError("a non-empty user account is required for the ACL")
    return [
        "icacls", str(path), "/inheritance:r", "/grant:r",
        f"{SECRET_ACL_SYSTEM}:{SECRET_ACL_RIGHTS}", f"{user}:{SECRET_ACL_RIGHTS}",
    ]


def lock_secret_file(path: Path | str, *, platform: str = sys.platform,
                     run=subprocess.run, user: str | None = None) -> list[str] | None:
    """Restrict path to SYSTEM + the current user (Windows) or chmod 0600.

    Returns the icacls argv that was run on Windows (None on POSIX). Raises
    OSError when the lockdown could not be applied so callers never continue
    with a world-readable key or token.
    """
    path = Path(path)
    if platform != "win32":
        os.chmod(path, 0o600)
        return None
    account = user if user is not None else current_user_account(platform, run=run)
    if not account:
        raise OSError(f"could not determine the current user to lock {path}")
    argv = secret_acl_argv(path, account)
    proc = run(argv, check=False, capture_output=True, text=True)
    if getattr(proc, "returncode", 1) != 0:
        detail = ((getattr(proc, "stderr", "") or getattr(proc, "stdout", "") or "")).strip()[:300]
        raise OSError(f"icacls lockdown failed for {path}: {detail}")
    return argv


def write_private_bytes(path: Path, data: bytes) -> None:
    """Create/overwrite a private key file: 0600 from the first byte, then ACL-locked."""
    path = Path(path)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    lock_secret_file(path)


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _name(common: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common)])


def _pem_key(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )


def _pem_cert(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def cert_fingerprint_pem(pem: bytes | str) -> str:
    cert = x509.load_pem_x509_certificate(
        pem.encode("utf-8") if isinstance(pem, str) else pem
    )
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def cert_fingerprint_der(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


class TlsMaterial:
    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir) / "tls"
        self.root.mkdir(parents=True, exist_ok=True)
        self.ca_key_path = self.root / "ca.key.pem"
        self.ca_cert_path = self.root / "ca.cert.pem"
        self.server_key_path = self.root / "server.key.pem"
        self.server_cert_path = self.root / "server.cert.pem"

    def ensure_ca_and_server(self) -> None:
        if not self.ca_cert_path.is_file():
            ca_key = _key()
            ca_cert = (
                x509.CertificateBuilder()
                .subject_name(_name("powerinfer-edge-ca"))
                .issuer_name(_name("powerinfer-edge-ca"))
                .public_key(ca_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(_now() - timedelta(minutes=1))
                .not_valid_after(_now() + timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
                .add_extension(
                    x509.KeyUsage(
                        digital_signature=False, content_commitment=False,
                        key_encipherment=False, data_encipherment=False,
                        key_agreement=False, key_cert_sign=True, crl_sign=True,
                        encipher_only=False, decipher_only=False,
                    ),
                    True,
                )
                .sign(ca_key, hashes.SHA256())
            )
            write_private_bytes(self.ca_key_path, _pem_key(ca_key))
            self.ca_cert_path.write_bytes(_pem_cert(ca_cert))
        if not self.server_cert_path.is_file():
            ca_key = serialization.load_pem_private_key(
                self.ca_key_path.read_bytes(), password=None
            )
            ca_cert = x509.load_pem_x509_certificate(self.ca_cert_path.read_bytes())
            server_key = _key()
            san = x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address(PHONE_BIND_HOST))]
            )
            server_cert = (
                x509.CertificateBuilder()
                .subject_name(_name("powerinfer-edge-gateway"))
                .issuer_name(ca_cert.subject)
                .public_key(server_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(_now() - timedelta(minutes=1))
                .not_valid_after(_now() + timedelta(days=825))
                .add_extension(san, False)
                .add_extension(
                    x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                    False,
                )
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
                .sign(ca_key, hashes.SHA256())
            )
            write_private_bytes(self.server_key_path, _pem_key(server_key))
            self.server_cert_path.write_bytes(_pem_cert(server_cert))

    def device_dir(self, device_id: str) -> Path:
        if not isinstance(device_id, str) or device_id in {".", ".."}:
            raise ValueError("device_id is invalid")
        if not _DEVICE_ID_RE.fullmatch(device_id):
            raise ValueError("device_id is invalid")
        root = (self.root / "devices").resolve()
        dest = (root / device_id).resolve()
        if dest.parent != root:
            raise ValueError("device_id is invalid")
        return dest

    def remove_device_material(self, device_id: str) -> None:
        dest = self.device_dir(device_id)
        if dest.is_dir():
            shutil.rmtree(dest)

    def issue_device_cert(self, device_id: str) -> tuple[bytes, bytes, str]:
        dest = self.device_dir(device_id)
        if dest.exists():
            raise ValueError("device_id already exists")
        self.ensure_ca_and_server()
        ca_key = serialization.load_pem_private_key(
            self.ca_key_path.read_bytes(), password=None
        )
        ca_cert = x509.load_pem_x509_certificate(self.ca_cert_path.read_bytes())
        key = _key()
        cert = (
            x509.CertificateBuilder()
            .subject_name(_name(device_id))
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_now() - timedelta(minutes=1))
            .not_valid_after(_now() + timedelta(days=825))
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
                False,
            )
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .sign(ca_key, hashes.SHA256())
        )
        cert_pem = _pem_cert(cert)
        key_pem = _pem_key(key)
        dest.mkdir(parents=True, exist_ok=False)
        (dest / "client.cert.pem").write_bytes(cert_pem)
        write_private_bytes(dest / "client.key.pem", key_pem)
        return cert_pem, key_pem, cert_fingerprint_pem(cert_pem)
