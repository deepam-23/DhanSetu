import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file, session
from flask_login import login_required, current_user
from ..extensions import db
from ..models import KycRecord, KycPdf, LoanApplication
from ..services.id_service import generate_kyc_id, qr_payload, sign_payload
from ..services.pdf_service import generate_kyc_pdf
import os
import base64
import hashlib
import io
import smtplib
from email.message import EmailMessage

bp = Blueprint("kyc", __name__)


@bp.post("/start")
@login_required
def start():
    existing = db.session.execute(db.select(KycRecord).filter_by(user_id=current_user.id)).scalar_one_or_none()
    if existing:
        return jsonify({"message": "KYC already started", "kyc_status": existing.status}), 200

    # Enforce eligibility: user must have a recent eligible loan draft
    last_loan = db.session.execute(
        db.select(LoanApplication)
        .filter_by(user_id=current_user.id)
        .order_by(LoanApplication.created_at.desc())
    ).scalars().first()
    if not last_loan or (last_loan.prediction or '').lower() != 'eligible':
        return jsonify({"error": "You are not eligible to start KYC. Please complete eligibility on the Loan page."}), 400

    kyc = KycRecord(user_id=current_user.id, status="pending")
    db.session.add(kyc)
    db.session.commit()
    return jsonify({"message": "KYC started", "kyc_id": kyc.id, "status": kyc.status})


@bp.post("/finalize")
@login_required
def finalize():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    dob_iso = (data.get("dob") or "").strip()
    gov_id = (data.get("gov_id") or "").strip()
    address = (data.get("address") or "").strip()
    # extra fields (not persisted in DB columns; included in PDF for record)
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    address2 = (data.get("address2") or "").strip()
    city = (data.get("city") or "").strip()
    state = (data.get("state") or "").strip()
    pincode = (data.get("pincode") or "").strip()
    id_issuer = (data.get("id_issuer") or "").strip()
    id_expiry = (data.get("id_expiry") or "").strip()

    kyc = db.session.execute(db.select(KycRecord).filter_by(user_id=current_user.id)).scalar_one_or_none()
    if not kyc:
        return jsonify({"error": "KYC not started"}), 400

    # Require OTP verifications
    if not session.get("otp_email_verified"):
        return jsonify({"error": "Please verify your email via OTP before finalizing."}), 400
    if not session.get("otp_phone_verified"):
        return jsonify({"error": "Please verify your phone via OTP before finalizing."}), 400

    kyc.kyc_id = generate_kyc_id(name, dob_iso, gov_id)
    kyc.name = name
    kyc.dob = dob_iso
    kyc.gov_id_type = data.get("gov_id_type") or "generic"
    kyc.gov_id_last4 = gov_id[-4:] if len(gov_id) >= 4 else gov_id
    kyc.address = address
    kyc.status = "verified"
    kyc.verified_at = datetime.utcnow()

    # First render a provisional PDF to compute checksum; then re-render with checksum in QR
    provisional_pdf_bytes, _ = generate_kyc_pdf({
        "KYC ID": kyc.kyc_id,
        "Name": name,
        "DOB": dob_iso,
        "Gov ID Type": kyc.gov_id_type,
        "Gov ID (last4)": kyc.gov_id_last4,
        "Email": email,
        "Phone": phone,
        "Address": address,
        "Address 2": address2,
        "City": city,
        "State": state,
        "Pincode": pincode,
        "ID Issuer": id_issuer,
        "ID Expiry": id_expiry,
    }, json.dumps({"note":"provisional"}), selfie_path=kyc.selfie_ref)

    # Now compute checksum of final PDF content with QR including checksum
    payload = qr_payload(kyc.kyc_id, "")
    payload["pdf_checksum"] = hashlib.sha256(provisional_pdf_bytes).hexdigest()
    signature = sign_payload(payload)
    qr_text = json.dumps({"payload": payload, "sig": signature})

    pdf_bytes, checksum = generate_kyc_pdf({
        "KYC ID": kyc.kyc_id,
        "Name": name,
        "DOB": dob_iso,
        "Gov ID Type": kyc.gov_id_type,
        "Gov ID (last4)": kyc.gov_id_last4,
        "Email": email,
        "Phone": phone,
        "Address": address,
        "Address 2": address2,
        "City": city,
        "State": state,
        "Pincode": pincode,
        "ID Issuer": id_issuer,
        "ID Expiry": id_expiry,
    }, qr_text, selfie_path=kyc.selfie_ref)

    payload["pdf_checksum"] = checksum
    signature = sign_payload(payload)
    qr_text = json.dumps({"payload": payload, "sig": signature})

    storage_dir = os.path.abspath(current_app.config.get("STORAGE_DIR", "storage"))
    os.makedirs(storage_dir, exist_ok=True)
    pdf_path = os.path.join(storage_dir, f"kyc_{kyc.kyc_id}.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    pdf = KycPdf(kyc_id=kyc.kyc_id, pdf_url=pdf_path, pdf_checksum=checksum, qr_payload_hash=signature)
    db.session.add(pdf)
    db.session.commit()

    return jsonify({"message": "KYC finalized", "kyc_id": kyc.kyc_id, "pdf_url": pdf_path})


@bp.post("/upload-selfie")
@login_required
def upload_selfie():
    data = request.get_json(silent=True) or {}
    b64 = data.get("image_data") or ""
    if not b64:
        return jsonify({"error": "No image data"}), 400
    # Accept data URL or plain base64
    if b64.startswith("data:image"):
        try:
            b64 = b64.split(",", 1)[1]
        except Exception:
            return jsonify({"error": "Invalid data URL"}), 400
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return jsonify({"error": "Invalid base64"}), 400

    kyc = db.session.execute(db.select(KycRecord).filter_by(user_id=current_user.id)).scalar_one_or_none()
    if not kyc:
        return jsonify({"error": "KYC not started"}), 400

    storage_dir = os.path.abspath(current_app.config.get("STORAGE_DIR", "storage"))
    os.makedirs(storage_dir, exist_ok=True)
    fname = f"selfie_{current_user.id}_{kyc.id}.png"
    path = os.path.join(storage_dir, fname)
    with open(path, "wb") as f:
        f.write(raw)

    kyc.selfie_ref = path
    db.session.commit()
    return jsonify({"message": "Selfie uploaded", "path": path})


# ---- OTP utilities ----
import random, time

def _store_otp(kind: str, value: str):
    code = f"{random.randint(0,999999):06d}"
    session[f"otp_{kind}_code"] = code
    session[f"otp_{kind}_for"] = (value or "").strip().lower()
    session[f"otp_{kind}_exp"] = int(time.time()) + 300
    session.modified = True
    return code

def _verify_otp(kind: str, value: str, code: str) -> bool:
    exp = session.get(f"otp_{kind}_exp") or 0
    if int(time.time()) > int(exp):
        return False
    if (session.get(f"otp_{kind}_for") or "") != (value or "").strip().lower():
        return False
    return (session.get(f"otp_{kind}_code") or "") == (code or "")


@bp.post("/otp/send")
@login_required
def otp_send():
    data = request.get_json() or {}
    channel = (data.get("channel") or "").lower()
    value = (data.get("value") or "").strip()
    if channel not in ("email", "phone") or not value:
        return jsonify({"error": "Invalid request"}), 400
    code = _store_otp(channel, value)
    # Send email via SMTP if configured; otherwise simulate
    if channel == "email":
        host = current_app.config.get("SMTP_HOST")
        user = current_app.config.get("SMTP_USER")
        pwd = current_app.config.get("SMTP_PASS")
        port = int(current_app.config.get("SMTP_PORT") or 587)
        from_email = current_app.config.get("FROM_EMAIL") or user or "no-reply@example.com"
        use_tls = bool(current_app.config.get("SMTP_TLS", True))
        if host and user and pwd:
            try:
                msg = EmailMessage()
                msg["Subject"] = "Your DhanSetu OTP"
                msg["From"] = from_email
                msg["To"] = value
                msg.set_content(f"Your OTP code is: {code}\nIt expires in 5 minutes.")
                with smtplib.SMTP(host, port, timeout=15) as s:
                    if use_tls:
                        s.starttls()
                    s.login(user, pwd)
                    s.send_message(msg)
                return jsonify({"message": "OTP sent to email"})
            except Exception as e:
                return jsonify({"error": f"Email send failed: {e}"}), 500
        # Fallback simulate if SMTP not configured
        return jsonify({"message": "OTP (email) generated; SMTP not configured", "debug": code})
    # Phone: still simulated
    return jsonify({"message": "OTP sent to phone", "debug": code})


@bp.post("/otp/verify")
@login_required
def otp_verify():
    data = request.get_json() or {}
    channel = (data.get("channel") or "").lower()
    value = (data.get("value") or "").strip()
    code = (data.get("code") or "").strip()
    if channel not in ("email", "phone") or not value or not code:
        return jsonify({"error": "Invalid request"}), 400
    ok = _verify_otp(channel, value, code)
    if not ok:
        return jsonify({"error": "Invalid or expired OTP"}), 400
    session[f"otp_{channel}_verified"] = True
    session.modified = True
    return jsonify({"message": f"{channel.capitalize()} verified"})


@bp.get("/me/pdf")
@login_required
def my_pdf():
    kyc = db.session.execute(db.select(KycRecord).filter_by(user_id=current_user.id)).scalar_one_or_none()
    if not kyc or not kyc.kyc_id:
        return jsonify({"error": "No KYC PDF"}), 404
    pdf = db.session.execute(
        db.select(KycPdf)
        .filter_by(kyc_id=kyc.kyc_id)
        .order_by(KycPdf.signed_at.desc())
        .limit(1)
    ).scalars().first()
    if not pdf:
        return jsonify({"error": "No KYC PDF"}), 404
    path = pdf.pdf_url
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    filename = f"kyc_{kyc.kyc_id}.pdf"
    return send_file(path, mimetype="application/pdf", as_attachment=True, download_name=filename)


@bp.get("/me")
@login_required
def my_kyc():
    kyc = db.session.execute(db.select(KycRecord).filter_by(user_id=current_user.id)).scalar_one_or_none()
    if not kyc:
        return jsonify({"exists": False})
    return jsonify({
        "exists": True,
        "kyc_id": kyc.kyc_id,
        "status": kyc.status,
        "verified_at": kyc.verified_at.isoformat() + "Z" if kyc.verified_at else "",
    })
