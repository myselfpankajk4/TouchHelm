"""Local HTTPS identity. No trust-store imports, network listeners or asset keys."""
import csv
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import ssl
import subprocess
import tempfile
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


class SecurePairingError(RuntimeError):
    pass


def private_storage_root():
    local = os.environ.get('LOCALAPPDATA')
    return Path(local) / 'TouchHelm' if local else Path.home() / '.touchhelm'


def protect_user_path(path):
    """Replace, rather than extend, the DACL: only the current user has access."""
    path = Path(path)
    if os.name != 'nt':
        path.chmod(0o700 if path.is_dir() else 0o600)
        return
    result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
        capture_output=True, text=True, timeout=3, check=True, creationflags=0x08000000)
    rows = list(csv.reader(result.stdout.splitlines()))
    sid = rows[0][-1].strip() if rows else ''
    if not re.fullmatch(r'S-1-\d+(?:-\d+)+', sid):
        raise SecurePairingError('Windows could not identify the private certificate owner.')
    api, kernel = ctypes.windll.advapi32, ctypes.windll.kernel32
    api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    api.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    api.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    api.SetFileSecurityW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    descriptor = ctypes.c_void_p()
    if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f'D:P(A;OICI;FA;;;{sid})', 1, ctypes.byref(descriptor), None):
        raise SecurePairingError('Windows could not create a private certificate ACL.')
    try:
        if not api.SetFileSecurityW(str(path), 0x80000004, descriptor):
            raise SecurePairingError('Windows could not protect the private certificate directory.')
    finally:
        kernel.LocalFree(descriptor)


class SecurePairingManager:
    def __init__(self, storage_dir=None, *, protector=protect_user_path):
        self.storage_dir = Path(storage_dir) if storage_dir is not None else private_storage_root() / 'certificates'
        self.ca_key_path = self.storage_dir / 'ca.key'
        self.certificate_path = self.storage_dir / 'TouchHelm-CA.crt'
        self.server_key_path = self.storage_dir / 'server.key'
        self.server_certificate_path = self.storage_dir / 'server.pem'
        self._protector = protector
        self._lock = threading.RLock()

    @staticmethod
    def _names(hosts):
        names = {'localhost': x509.DNSName('localhost'),
                 '127.0.0.1': x509.IPAddress(ipaddress.ip_address('127.0.0.1')),
                 '::1': x509.IPAddress(ipaddress.ip_address('::1'))}
        for host in hosts:
            if not isinstance(host, str) or not host or len(host) > 253:
                raise ValueError('Invalid certificate host')
            host = host.strip('[]').lower()
            try:
                names[host] = x509.IPAddress(ipaddress.ip_address(host))
            except ValueError:
                if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host):
                    raise ValueError('Invalid certificate host')
                names[host] = x509.DNSName(host)
        return [names[key] for key in sorted(names)]

    def _write(self, path, data):
        descriptor, temporary = tempfile.mkstemp(dir=self.storage_dir, suffix='.tmp')
        try:
            self._protector(Path(temporary))
            with os.fdopen(descriptor, 'wb') as stream:
                descriptor = None
                stream.write(data)
            os.replace(temporary, path)
            self._protector(path)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _key_bytes(key):
        return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())

    def _ca(self, now):
        present = (self.ca_key_path.exists(), self.certificate_path.exists())
        if any(present) and not all(present):
            raise SecurePairingError('Stored local CA is incomplete; restore its certificate and key before enabling HTTPS.')
        if all(present):
            try:
                key = serialization.load_pem_private_key(self.ca_key_path.read_bytes(), password=None)
                cert = x509.load_der_x509_certificate(self.certificate_path.read_bytes())
                if cert.not_valid_after_utc <= now:
                    raise ValueError('expired')
                if key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo):
                    raise ValueError('mismatched key')
                if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
                    raise ValueError('not a CA')
                return key, cert
            except Exception as error:
                raise SecurePairingError('Stored local CA is invalid; HTTPS was not enabled.') from error
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'TouchHelm Local CA')])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
        self._write(self.ca_key_path, self._key_bytes(key))
        self._write(self.certificate_path, cert.public_bytes(serialization.Encoding.DER))
        return key, cert

    def prepare(self, hosts):
        names = self._names(hosts)
        with self._lock:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self._protector(self.storage_dir)
            # Repair permissions on pre-existing files before reading their keys.
            for path in (self.ca_key_path, self.certificate_path, self.server_key_path, self.server_certificate_path):
                if path.exists(): self._protector(path)
            now = datetime.now(timezone.utc)
            ca_key, ca_cert = self._ca(now)
            valid = False
            if self.server_key_path.exists() and self.server_certificate_path.exists():
                try:
                    leaf = x509.load_pem_x509_certificate(self.server_certificate_path.read_bytes())
                    leaf_key = serialization.load_pem_private_key(self.server_key_path.read_bytes(), password=None)
                    ca_cert.public_key().verify(leaf.signature, leaf.tbs_certificate_bytes, ec.ECDSA(leaf.signature_hash_algorithm))
                    valid = (leaf.not_valid_after_utc > now + timedelta(days=7)
                        and leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value == x509.SubjectAlternativeName(names)
                        and leaf_key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) == leaf.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
                except Exception:
                    pass
            if not valid:
                key = ec.generate_private_key(ec.SECP256R1())
                leaf = (x509.CertificateBuilder()
                    .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'TouchHelm Host')]))
                    .issuer_name(ca_cert.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
                    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                    .add_extension(x509.SubjectAlternativeName(names), critical=False)
                    .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                    .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
                    .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
                    .sign(ca_key, hashes.SHA256()))
                self._write(self.server_key_path, self._key_bytes(key))
                self._write(self.server_certificate_path, leaf.public_bytes(serialization.Encoding.PEM))
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(self.server_certificate_path), str(self.server_key_path))
            return context

    def public_certificate_der(self):
        return self.certificate_path.read_bytes()

    def public_certificate_pem(self):
        return x509.load_der_x509_certificate(self.public_certificate_der()).public_bytes(serialization.Encoding.PEM)

    def public_info(self):
        raw = self.public_certificate_der()
        fingerprint = hashlib.sha256(raw).hexdigest().upper()
        cert = x509.load_der_x509_certificate(raw)
        return {'https_port': 8766, 'certificate_name': 'TouchHelm-CA.crt',
            'fingerprint_sha256': ':'.join(fingerprint[index:index + 2] for index in range(0, len(fingerprint), 2)),
            'expires_at': cert.not_valid_after_utc.isoformat(),
            'trust_guide': [
                'Open this PC’s phone interface, choose Settings → Secure pairing, and download TouchHelm-CA.crt.',
                'Compare its SHA-256 fingerprint with the fingerprint shown here.',
                'In Android Settings, search “Install a certificate”, choose CA certificate, and select TouchHelm-CA.crt. Menu names vary by device.',
                'Only trust this certificate if you control this PC. TouchHelm does not install trust automatically.',
                'Open the HTTPS address after installation, enter your PIN if required, and confirm Chrome reports a secure connection.',
                'Remove the TouchHelm CA from Android’s user credentials when you no longer use this PC.']}
