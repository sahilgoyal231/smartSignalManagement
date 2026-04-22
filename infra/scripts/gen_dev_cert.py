"""
Certificate Generator — Dev/Test Helper
=========================================
Generates a self-signed ECDSA-P256 X.509 certificate + private key
for local development and testing.

In production, certificates are issued by the SmartSignal CA and
provisioned at manufacturing time via secure boot.

Usage:
    python infra/scripts/gen_dev_cert.py --id AMB-MH-042 --out vsu/certs/

Outputs:
    vsu/certs/vsu.key  — ECDSA-P256 private key (PEM)
    vsu/certs/vsu.crt  — Self-signed X.509 certificate (PEM, 10 years)
"""
import argparse
import datetime
import os
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def generate_dev_cert(vehicle_id: str, out_dir: str) -> None:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    key_file  = out_path / "vsu.key"
    cert_file = out_path / "vsu.crt"

    print(f"🔑 Generating ECDSA-P256 private key...")
    private_key = ec.generate_private_key(ec.SECP256R1())

    print(f"📜 Generating self-signed X.509 certificate for {vehicle_id}...")
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME,         vehicle_id),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME,   "SmartSignal"),
        x509.NameAttribute(NameOID.COUNTRY_NAME,        "IN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Maharashtra"),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))  # 10 years
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(vehicle_id),
            ]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    # Write private key
    with open(key_file, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    # Write certificate
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    # Print fingerprint
    import hashlib
    cert_pem = cert_file.read_text()
    fingerprint = hashlib.sha256(cert_pem.encode()).hexdigest()

    print(f"\n✅ Generated!")
    print(f"   Key:         {key_file}")
    print(f"   Certificate: {cert_file}")
    print(f"   Subject CN:  {vehicle_id}")
    print(f"   Valid:       10 years")
    print(f"   Fingerprint: {fingerprint[:32]}...")
    print(f"\n📋 Next step: Register this certificate with the vehicle registry:")
    print(f"   POST /api/v1/vehicles (include vsu_cert_pem field)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate dev VSU certificate")
    parser.add_argument("--id",  required=True, help="Vehicle ID e.g. AMB-MH-042")
    parser.add_argument("--out", default="vsu/certs", help="Output directory")
    args = parser.parse_args()
    generate_dev_cert(args.id, args.out)
