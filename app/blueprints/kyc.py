import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from ..extensions import db
from ..models import KycRecord, KycPdf
from ..services.id_service import generate_kyc_id, qr_payload, sign_payload
from ..services.pdf_service import generate_kyc_pdf
import os
import io

bp = Blueprint("kyc", __name__)


@bp.post("/start")
@login_required
def start():
    existing = db.session.execute(db.select(KycRecord).filter_by(user_id=current_user.id)).scalar_one_or_none()
    if existing:
        return jsonify({"message": "KYC already started", "kyc_status": existing.status}), 200

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

    kyc.kyc_id = generate_kyc_id(name, dob_iso, gov_id)
    kyc.name = name
    kyc.dob = dob_iso
    kyc.gov_id_type = data.get("gov_id_type") or "generic"
    kyc.gov_id_last4 = gov_id[-4:] if len(gov_id) >= 4 else gov_id
    kyc.address = address
    kyc.status = "verified"
    kyc.verified_at = datetime.utcnow()

    # Build PDF and store
    payload = qr_payload(kyc.kyc_id, "")
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
    }, qr_text)

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
