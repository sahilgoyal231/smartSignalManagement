"""
Unit Tests — Step 5: ECDSA Signer, LoRa TX, BLE Beacon
==========================================================
All tests run without hardware (mock / ephemeral keys).

Run:
    pytest vsu/tests/test_step5.py -v
"""
import json
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

from vsu.src.beacon_signer import (
    BeaconSigner, BeaconVerifier, _canonical_bytes
)
from vsu.src.ble_beacon import encode_ble_payload, decode_ble_payload
from vsu.src.lora_tx import LoRaTX


# ─────────────────────────────────────────────────────────────
# Shared fixture
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def sample_payload():
    return {
        "v":            1,
        "vehicle_id":   "AMB-MH-042",
        "vehicle_type": "AMBULANCE",
        "priority":     2,
        "city":         "Mumbai",
        "ts":           "2026-03-06T14:50:00.000Z",
        "gps": {
            "lat": 19.0654, "lon": 72.8647, "alt": 12.0,
            "spd": 62.4,    "hdg": 275.3,   "acc": 2.5,
            "sat": 10,      "fix": 1,       "src": "gps",
        },
        "siren":  True,
        "bat":    85,
        "dest":   {"lat": 19.0456, "lon": 72.8272},
        "nonce":  "abc123def456abc7890deadbeef1234",
        "sig":    None,
    }


@pytest.fixture
def ephemeral_signer(tmp_path):
    """Returns a BeaconSigner using a freshly-generated ephemeral key."""
    key_path  = str(tmp_path / "vsu.key")
    cert_path = str(tmp_path / "vsu.crt")
    # Non-existent paths → signer creates an ephemeral key automatically
    return BeaconSigner(key_path, cert_path)


# ─────────────────────────────────────────────────────────────
# ECDSA Signer tests
# ─────────────────────────────────────────────────────────────

class TestBeaconSigner:

    def test_sign_sets_sig_field(self, ephemeral_signer, sample_payload):
        signed = ephemeral_signer.sign(sample_payload)
        assert signed["sig"] is not None
        assert isinstance(signed["sig"], str)
        assert len(signed["sig"]) > 60   # DER signatures are 70–72 hex chars

    def test_sig_is_valid_hex(self, ephemeral_signer, sample_payload):
        signed = ephemeral_signer.sign(sample_payload)
        # Should not raise
        bytes.fromhex(signed["sig"])

    def test_canonical_bytes_excludes_sig(self, sample_payload):
        sample_payload["sig"] = "some_existing_sig"
        canon = _canonical_bytes(sample_payload)
        assert b"sig" not in canon

    def test_canonical_bytes_is_deterministic(self, sample_payload):
        a = _canonical_bytes(sample_payload)
        b = _canonical_bytes(sample_payload)
        assert a == b

    def test_signing_does_not_mutate_other_fields(self, ephemeral_signer, sample_payload):
        original_ts = sample_payload["ts"]
        signed = ephemeral_signer.sign(sample_payload)
        assert signed["ts"]         == original_ts
        assert signed["vehicle_id"] == "AMB-MH-042"
        assert signed["bat"]        == 85


# ─────────────────────────────────────────────────────────────
# ECDSA Verifier tests
# ─────────────────────────────────────────────────────────────

class TestBeaconVerifier:

    def _make_signer_and_verifier(self, tmp_path, vehicle_id="AMB-MH-042"):
        """
        Generate a real key pair, build a verifier with the public key.
        """
        # Generate key and cert
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.x509.oid import NameOID
        import datetime

        private_key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, vehicle_id)])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject).issuer_name(subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=365))
            .sign(private_key, hashes.SHA256())
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()

        # Write key
        key_file  = tmp_path / "vsu.key"
        cert_file = tmp_path / "vsu.crt"
        key_file.write_bytes(private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()
        ))
        cert_file.write_text(cert_pem)

        signer   = BeaconSigner(str(key_file), str(cert_file))
        verifier = BeaconVerifier()
        verifier.load_cert_pem(vehicle_id, cert_pem)
        return signer, verifier

    def test_valid_signature_passes(self, tmp_path, sample_payload):
        signer, verifier = self._make_signer_and_verifier(tmp_path)
        signed = signer.sign(sample_payload)
        ok, reason = verifier.verify(signed)
        assert ok is True
        assert reason == "OK"

    def test_unknown_vehicle_rejected(self, sample_payload):
        verifier = BeaconVerifier()  # empty store
        sample_payload["sig"] = "00" * 35
        ok, reason = verifier.verify(sample_payload)
        assert ok is False
        assert "UNKNOWN_VEHICLE" in reason

    def test_tampered_payload_rejected(self, tmp_path, sample_payload):
        signer, verifier = self._make_signer_and_verifier(tmp_path)
        signed = signer.sign(sample_payload)
        # Tamper with speed after signing
        signed["gps"]["spd"] = 999.9
        ok, reason = verifier.verify(signed)
        assert ok is False
        assert "INVALID_SIGNATURE" in reason

    def test_replay_attack_rejected(self, tmp_path, sample_payload):
        signer, verifier = self._make_signer_and_verifier(tmp_path)
        signed = signer.sign(sample_payload)
        # First verify: OK
        ok1, _ = verifier.verify(signed)
        assert ok1 is True
        # Second verify with SAME nonce: replay
        ok2, reason2 = verifier.verify(signed)
        assert ok2 is False
        assert "REPLAY" in reason2

    def test_different_nonces_both_pass(self, tmp_path, sample_payload):
        signer, verifier = self._make_signer_and_verifier(tmp_path)
        import secrets
        # Build two payloads with different nonces
        p1 = dict(sample_payload); p1["nonce"] = secrets.token_hex(16)
        p2 = dict(sample_payload); p2["nonce"] = secrets.token_hex(16)
        signer.sign(p1)
        signer.sign(p2)
        ok1, _ = verifier.verify(p1)
        ok2, _ = verifier.verify(p2)
        assert ok1 and ok2


# ─────────────────────────────────────────────────────────────
# BLE Beacon tests
# ─────────────────────────────────────────────────────────────

class TestBLEBeacon:

    def test_encode_decode_roundtrip(self):
        payload = encode_ble_payload(
            vehicle_id="AMB-MH-042",
            priority=2, lat=19.0654, lon=72.8647,
            siren=True, gps_valid=True
        )
        assert len(payload) == 19

        decoded = decode_ble_payload(payload)
        assert decoded["vehicle_id"] == "AMB-MH"   # 6 chars
        assert decoded["priority"]   == 2
        assert decoded["siren"]      is True
        assert decoded["gps_valid"]  is True
        assert decoded["lat"]  == pytest.approx(19.0654, abs=1e-5)
        assert decoded["lon"]  == pytest.approx(72.8647, abs=1e-5)

    def test_siren_flag_encoding(self):
        with_siren    = encode_ble_payload("TEST-01", 2, 0.0, 0.0, True,  True)
        without_siren = encode_ble_payload("TEST-01", 2, 0.0, 0.0, False, True)
        d_with    = decode_ble_payload(with_siren)
        d_without = decode_ble_payload(without_siren)
        assert d_with["siren"]    is True
        assert d_without["siren"] is False

    def test_payload_exactly_19_bytes(self):
        p = encode_ble_payload("AMB-MH-042", 3, 28.6139, 77.2090, False, True)
        assert len(p) == 19

    def test_short_vehicle_id_padded(self):
        p = encode_ble_payload("AB", 1, 0.0, 0.0, False, False)
        d = decode_ble_payload(p)
        assert d["vehicle_id"] == "AB"   # nulls stripped on decode

    def test_decode_raises_on_short_input(self):
        with pytest.raises(ValueError, match="too short"):
            decode_ble_payload(b"\x00" * 10)


# ─────────────────────────────────────────────────────────────
# LoRa TX tests
# ─────────────────────────────────────────────────────────────

class TestLoRaTX:

    @pytest.fixture
    def mock_config(self):
        cfg = MagicMock()
        cfg.lora_frequency_mhz     = 433.0
        cfg.lora_tx_power_dbm      = 17
        cfg.lora_spreading_factor  = 9
        cfg.lora_bandwidth_khz     = 125.0
        cfg.lora_coding_rate       = "4/5"
        cfg.lora_beacon_interval_s = 0.5
        return cfg

    def test_mock_mode_transmits_without_hardware(self, mock_config):
        tx = LoRaTX(mock_config)
        tx._mock = True
        tx._running = True
        with patch("time.sleep"):
            tx._send_packet(b"\x00" * 14)
        assert tx.tx_count == 1

    def test_queue_backpressure_drops_oldest(self, mock_config):
        tx = LoRaTX(mock_config)
        tx._mock = True
        # Fill queue beyond limit (5)
        for i in range(7):
            tx.transmit(bytes([i] * 14))
        assert len(tx._tx_queue) <= 5

    def test_stats_returns_dict(self, mock_config):
        tx = LoRaTX(mock_config)
        s = tx.stats()
        assert "tx_count"  in s
        assert "mock_mode" in s
        assert "queue_len" in s

    def test_airtime_mock_logs_hex(self, mock_config, capsys):
        tx = LoRaTX(mock_config)
        tx._mock = True
        # Call with captured sleep to avoid actual delay
        with patch("time.sleep"):
            tx._mock_transmit(bytes.fromhex("0b5d26c52b6e456502580abec802"))
        assert tx.tx_count == 1
