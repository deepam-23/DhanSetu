import base64
import hashlib
from datetime import datetime
from flask import current_app


def generate_kyc_id(name: str, dob_iso: str, gov_id: str) -> str:
    norm = (name or "").strip().lower() + "|" + (dob_iso or "").strip() + "|" + (gov_id or "").strip()
    salt = current_app.config.get("SERVER_SALT", "change-me")
    digest = hashlib.sha256((norm + "|" + salt).encode("utf-8")).digest()
    return base64.b32encode(digest)[:12].decode("ascii")


def qr_payload(kyc_id: str, pdf_checksum: str) -> dict:
    return {
        "kyc_id": kyc_id,
        "issued_at": datetime.utcnow().isoformat() + "Z",
        "pdf_checksum": pdf_checksum,
    }


def sign_payload(payload: dict) -> str:
    secret = current_app.config.get("SERVER_SIGNING_SECRET", "change-me").encode("utf-8")
    body = (payload.get("kyc_id", "") + "|" + payload.get("issued_at", "") + "|" + payload.get("pdf_checksum", "")).encode("utf-8")
    return hashlib.sha256(secret + body).hexdigest()
