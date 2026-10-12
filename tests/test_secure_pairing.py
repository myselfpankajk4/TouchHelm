"""Certificate tests use temporary files and a fake ACL protector, never trust stores."""
import hashlib
import importlib
import ipaddress
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import Mock
from cryptography import x509
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[1]


class SecurePairingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=ROOT / 'tests')
        self.addCleanup(self.folder.cleanup)
        self.module = importlib.import_module('server.secure_pairing')
        self.protect = Mock()
        self.manager = self.module.SecurePairingManager(self.folder.name, protector=self.protect)

    def test_server_certificate_covers_lan_and_loopback_and_ca_is_installable(self):
        context = self.manager.prepare(['192.168.1.12', 'host.local'])
        cert = x509.load_pem_x509_certificate(self.manager.server_certificate_path.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        self.assertIn(ipaddress.ip_address('192.168.1.12'), san.get_values_for_type(x509.IPAddress))
        self.assertIn(ipaddress.ip_address('127.0.0.1'), san.get_values_for_type(x509.IPAddress))
        self.assertIn('host.local', san.get_values_for_type(x509.DNSName))
        ca = x509.load_der_x509_certificate(self.manager.public_certificate_der())
        self.assertTrue(ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        self.assertEqual(cert.issuer, ca.subject)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.protect.assert_called()

    def test_existing_ca_and_leaf_survive_normal_restarts(self):
        self.manager.prepare(['192.168.1.12'])
        ca, leaf = self.manager.public_certificate_der(), self.manager.server_certificate_path.read_bytes()
        self.manager.prepare(['192.168.1.12'])
        self.assertEqual(self.manager.public_certificate_der(), ca)
        self.assertEqual(self.manager.server_certificate_path.read_bytes(), leaf)

    def test_changed_lan_address_renews_leaf_without_replacing_trusted_ca(self):
        self.manager.prepare(['192.168.1.12'])
        ca, leaf = self.manager.public_certificate_der(), self.manager.server_certificate_path.read_bytes()
        self.manager.prepare(['192.168.2.14'])
        self.assertEqual(self.manager.public_certificate_der(), ca)
        self.assertNotEqual(self.manager.server_certificate_path.read_bytes(), leaf)

    def test_public_info_contains_ca_fingerprint_and_no_private_paths_or_key_material(self):
        self.manager.prepare(['192.168.1.12'])
        info = self.manager.public_info()
        self.assertEqual(info['fingerprint_sha256'].replace(':', ''),
                         hashlib.sha256(self.manager.public_certificate_der()).hexdigest().upper())
        self.assertTrue(info['trust_guide'])
        public = str(info)
        self.assertNotIn(self.folder.name, public)
        self.assertNotIn('PRIVATE KEY', public)
        self.assertNotIn('server_key_path', info)

    def test_incomplete_ca_is_not_silently_replaced(self):
        self.manager.prepare(['192.168.1.12'])
        self.manager.ca_key_path.unlink()
        with self.assertRaisesRegex(self.module.SecurePairingError, 'incomplete'):
            self.manager.prepare(['192.168.1.12'])

    def test_acl_failure_prevents_writing_any_private_key(self):
        self.protect.side_effect = PermissionError('ACL unavailable')
        with self.assertRaises(PermissionError):
            self.manager.prepare(['192.168.1.12'])
        self.assertFalse(self.manager.ca_key_path.exists())

    def test_invalid_host_is_rejected_before_certificate_files_are_created(self):
        with self.assertRaises(ValueError):
            self.manager.prepare(['bad\nsubject'])
        self.assertFalse(self.manager.ca_key_path.exists())


if __name__ == '__main__':
    unittest.main()
