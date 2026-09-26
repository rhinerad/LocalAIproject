"""Local CA + server/device certificates for G2 mTLS. Workstation files only."""
from __future__ import annotations

import hashlib
import ipaddress
import re
import shutil
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
            self.ca_key_path.write_bytes(_pem_key(ca_key))
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
            self.server_key_path.write_bytes(_pem_key(server_key))
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
        (dest / "client.key.pem").write_bytes(key_pem)
        return cert_pem, key_pem, cert_fingerprint_pem(cert_pem)
