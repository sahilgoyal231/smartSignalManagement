"""
ECDSA-P256 Beacon Signer
=========================
Signs each beacon payload with the VSU's private key (ECDSA over NIST P-256).
The edge node verifies the signature using the vehicle's X.509 certificate
registered in the cloud Vehicle Registry.

Security guarantees:
  - Authenticity:  Only the legitimate VSU with the correct private key can sign
  - Integrity:     Tampering with any field invalidates the signature
  - Non-repudiation: Signed events are legally attributable to the registered vehicle
  - Replay prevention: Nonce is included in the signed data; edge node caches nonces

Signing process:
  1. Build canonical string from payload fields (deterministic ordering)
  2. SHA-256 hash the canonical bytes
  3. Sign hash with ECDSA-P256 private key → (r, s) encoded as DER hex string
  4. Attach hex signature to payload["sig"]

Verification (edge node side):
  1. Extract sig, rebuild canonical string from payload
  2. Verify DER signature against vehicle's public key from cert store
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature, encode_dss_signature
)
from cryptography.x509 import load_pem_x509_certificate
from cryptography.exceptions import InvalidSignature
from loguru import logger


# ─────────────────────────────────────────────────────────────
# Canonical payload builder (deterministic field ordering)
# ─────────────────────────────────────────────────────────────

_SIGNED_FIELDS = ("v", "vehicle_id", "vehicle_type", "priority", "city",
                  "ts", "gps", "siren", "bat", "dest", "nonce")


def _canonical_bytes(payload: dict) -> bytes:
    """
    Build a deterministic UTF-8 byte string of the fields to sign.
    Uses compact JSON with sorted keys — same result on any platform.
    The 'sig' field is intentionally excluded (it's not in _SIGNED_FIELDS).
    """
    subset = {k: payload[k] for k in _SIGNED_FIELDS if k in payload}
    return json.dumps(subset, separators=(",", ":"), sort_keys=True).encode("utf-8")


# ─────────────────────────────────────────────────────────────
# Signer (VSU side)
# ─────────────────────────────────────────────────────────────

class BeaconSigner:
    """
    Loads the VSU's ECDSA-P256 private key and signs each beacon payload.

    Key provisioning (done once at manufacturing / registration):
        openssl ecparam -name prime256v1 -genkey -noout -out vsu.key
        openssl req -new -x509 -key vsu.key -out vsu.crt -days 3650 \\
            -subj "/CN=AMB-MH-042/O=SmartSignal/C=IN"
        # Upload vsu.crt PEM to Vehicle Registry API at registration time
    """

    def __init__(self, key_path: str, cert_path: str) -> None:
        self._private_key  = self._load_private_key(key_path)
        self._cert_pem     = self._load_cert_pem(cert_path)
        self._cert_hash    = self._fingerprint(self._cert_pem)
        logger.success(
            f"BeaconSigner: Loaded key from {key_path} "
            f"(cert fingerprint: {self._cert_hash[:16]}...)"
        )

    # ─────────────────────────────────────────────
    # Public
    # ─────────────────────────────────────────────

    def sign(self, payload: dict) -> dict:
        """
        Signs the payload in-place, setting payload['sig'] to a hex DER string.
        Returns the modified payload dict.
        """
        canonical = _canonical_bytes(payload)
        # ECDSA sign with SHA-256
        der_sig = self._private_key.sign(canonical, ec.ECDSA(hashes.SHA256()))
        payload["sig"] = der_sig.hex()
        return payload

    def get_cert_pem(self) -> str:
        """Return the PEM certificate string (for registration with cloud API)."""
        return self._cert_pem

    def get_cert_hash(self) -> str:
        """Return SHA-256 fingerprint of the certificate (hex string)."""
        return self._cert_hash

    # ─────────────────────────────────────────────
    # Private loaders
    # ─────────────────────────────────────────────

    @staticmethod
    def _load_private_key(path: str) -> ec.EllipticCurvePrivateKey:
        p = Path(path)
        if not p.exists():
            logger.warning(f"BeaconSigner: Key not found at {path} — using EPHEMERAL dev key (NOT for production!)")
            return ec.generate_private_key(ec.SECP256R1())
        with open(p, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError("Expected ECDSA private key, got different key type")
        logger.debug(f"BeaconSigner: Private key loaded from {path}")
        return key

    @staticmethod
    def _load_cert_pem(path: str) -> str:
        p = Path(path)
        if not p.exists():
            logger.warning(f"BeaconSigner: Cert not found at {path} — returning empty string")
            return ""
        with open(p, "r") as f:
            return f.read()

    @staticmethod
    def _fingerprint(pem: str) -> str:
        if not pem:
            return "NO_CERT"
        return hashlib.sha256(pem.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────
# Verifier (Edge Node side — used in edge-node module)
# ─────────────────────────────────────────────────────────────

class BeaconVerifier:
    """
    Verifies beacon signatures using the vehicle's registered public key.
    Used by the edge node to authenticate incoming beacons.

    The edge node maintains a local cert cache loaded from the cloud at
    startup (and refreshed on OTA update / new vehicle registration).
    """

    def __init__(self) -> None:
        # cert_store: {vehicle_id -> ec.EllipticCurvePublicKey}
        self._cert_store: dict[str, ec.EllipticCurvePublicKey] = {}
        # Nonce cache: {vehicle_id -> set of recent nonces}
        self._nonce_cache: dict[str, set] = {}
        self._nonce_window = 120  # seconds — we use a simple rolling set here

    def load_cert_pem(self, vehicle_id: str, cert_pem: str) -> None:
        """Load a vehicle's PEM certificate into the local store."""
        try:
            cert = load_pem_x509_certificate(cert_pem.encode())
            pub_key = cert.public_key()
            if not isinstance(pub_key, ec.EllipticCurvePublicKey):
                raise ValueError("Certificate must use ECDSA key")
            self._cert_store[vehicle_id] = pub_key
            logger.debug(f"BeaconVerifier: Loaded cert for {vehicle_id}")
        except Exception as exc:
            logger.error(f"BeaconVerifier: Failed to load cert for {vehicle_id}: {exc}")

    def verify(self, payload: dict) -> tuple[bool, str]:
        """
        Verifies a beacon payload.

        Returns:
            (True, "OK")                        — valid signature, fresh nonce
            (False, reason_string)              — verification failed

        Checks (in order):
            1. vehicle_id is registered (cert in store)
            2. nonce has not been seen before (replay prevention)
            3. ECDSA signature is valid
        """
        vehicle_id = payload.get("vehicle_id", "")
        sig_hex    = payload.get("sig", "")
        nonce      = payload.get("nonce", "")

        # ── 1. Certificate check ──────────────────────
        if vehicle_id not in self._cert_store:
            return False, f"UNKNOWN_VEHICLE:{vehicle_id}"

        # ── 2. Replay check ───────────────────────────
        if vehicle_id not in self._nonce_cache:
            self._nonce_cache[vehicle_id] = set()
        if nonce in self._nonce_cache[vehicle_id]:
            return False, f"REPLAY_DETECTED:nonce={nonce[:8]}..."
        self._nonce_cache[vehicle_id].add(nonce)

        # Prune nonce cache if too large (simple LRU approximation)
        if len(self._nonce_cache[vehicle_id]) > 500:
            self._nonce_cache[vehicle_id] = set(
                list(self._nonce_cache[vehicle_id])[-250:]
            )

        # ── 3. ECDSA signature verification ──────────
        try:
            pub_key   = self._cert_store[vehicle_id]
            canonical = _canonical_bytes(payload)
            sig_bytes = bytes.fromhex(sig_hex)
            pub_key.verify(sig_bytes, canonical, ec.ECDSA(hashes.SHA256()))
            return True, "OK"
        except InvalidSignature:
            return False, "INVALID_SIGNATURE"
        except Exception as exc:
            return False, f"VERIFY_ERROR:{exc}"

    def is_registered(self, vehicle_id: str) -> bool:
        return vehicle_id in self._cert_store

    def registered_vehicles(self) -> list[str]:
        return list(self._cert_store.keys())
