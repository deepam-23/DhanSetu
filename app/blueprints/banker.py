import json
import os
import hashlib
from flask import Blueprint, jsonify, request, send_file
from datetime import datetime, timedelta
from collections import defaultdict
from flask import session
from werkzeug.utils import secure_filename
from ..extensions import db, limiter
from ..models import KycRecord, KycPdf, LoanApplication, User
from sqlalchemy import func
from ..services.id_service import sign_payload

bp = Blueprint("banker", __name__)

@bp.before_request
def require_banker_session():
    # Protect all banker APIs; allow GET to /banker page (rendered in web.py) only
    # This blueprint only serves APIs; enforce banker session for all requests
    if session.get("banker_id") is None:
        # Return JSON for API endpoints
        return jsonify({"error": "Unauthorized banker"}), 401

@bp.get("/me")
def me():
    return jsonify({
        "banker_id": session.get("banker_id"),
        "banker_email": session.get("banker_email"),
        "banker_role": session.get("banker_role")
    })

@bp.get("/kyc/<string:kyc_id>")
@limiter.limit("30/minute")
def lookup(kyc_id: str):
    try:
        raw = (kyc_id or "").strip()
        norm_id = raw.replace(" ", "").replace("-", "").upper()
        if not norm_id:
            return jsonify({"error": "Invalid KYC ID"}), 400
        kyc = None
        # If the input looks like a numeric internal ID, resolve it first
        if norm_id.isdigit():
            # Primary key lookup is unique; use session.get for safety
            kyc = db.session.get(KycRecord, int(norm_id))
            if kyc and kyc.kyc_id:
                norm_id = kyc.kyc_id
        if kyc is None:
            # Be robust against accidental duplicates: pick the most recent
            query = db.select(KycRecord).filter_by(kyc_id=norm_id).order_by(KycRecord.created_at.desc())
            kyc = db.session.execute(query).scalars().first()
        if not kyc:
            return jsonify({"error": "KYC not found"}), 404
        
        # Get user information for genuine user verification
        user = db.session.get(User, kyc.user_id) if kyc.user_id else None
        
        # Get PDF information
        pdf = db.session.execute(
            db.select(KycPdf).filter_by(kyc_id=norm_id).order_by(KycPdf.id.desc())
        ).scalars().first()
        
        payload = {"kyc_id": kyc.kyc_id, "issued_at": kyc.verified_at.isoformat() + "Z" if kyc.verified_at else "", "pdf_checksum": pdf.pdf_checksum if pdf else ""}
        sig = sign_payload(payload)

        return jsonify({
            "kyc_id": kyc.kyc_id,
            "full_name": kyc.name,
            "email": user.email if user else "",
            "phone": user.phone if user else "",
            "dob": kyc.dob,
            "status": kyc.status,
            "verified": kyc.status == "verified",
            "created_at": kyc.created_at.isoformat() + "Z" if kyc.created_at else "",
            "pdf_checksum": pdf.pdf_checksum if pdf else "",
            "verification_signature": sig,
            "loan_id": (db.session.execute(db.select(LoanApplication).filter_by(user_id=kyc.user_id).order_by(LoanApplication.created_at.desc()).limit(1)).scalars().first().id if kyc.user_id else None)
        })
    except Exception as e:
        return jsonify({"error": f"Lookup failed: {str(e) or 'unknown'}"}), 400

@bp.get("/kyc/<string:kyc_id>/pdf")
@limiter.limit("30/minute")
def download_pdf(kyc_id: str):
    # Normalize and resolve
    raw = (kyc_id or "").strip()
    norm_id = raw.replace(" ", "").replace("-", "").upper()
    if not norm_id:
        return jsonify({"error": "Invalid KYC ID"}), 400
    kyc = None
    if norm_id.isdigit():
        kyc = db.session.get(KycRecord, int(norm_id))
        if kyc and kyc.kyc_id:
            norm_id = kyc.kyc_id
    if kyc is None:
        kyc = db.session.execute(
            db.select(KycRecord).filter_by(kyc_id=norm_id).order_by(KycRecord.created_at.desc())
        ).scalars().first()
    if not kyc:
        return jsonify({"error": "KYC not found"}), 404
    pdf = db.session.execute(
        db.select(KycPdf).filter_by(kyc_id=norm_id).order_by(KycPdf.id.desc())
    ).scalars().first()
    if not pdf or not pdf.pdf_url:
        return jsonify({"error": "KYC PDF not found"}), 404
    try:
        return send_file(pdf.pdf_url, as_attachment=True, download_name=f"{norm_id}.pdf")
    except Exception as e:
        return jsonify({"error": f"Failed to send PDF: {str(e) or 'unknown'}"}), 400

# ----- Analytics for banker dashboard -----

@bp.get("/analytics/summary")
def analytics_summary():
    total_kyc = db.session.execute(db.select(func.count()).select_from(KycRecord)).scalar() or 0
    verified_kyc = db.session.execute(
        db.select(func.count()).select_from(KycRecord).filter(KycRecord.status == "verified")
    ).scalar() or 0
    total_loans = db.session.execute(db.select(func.count()).select_from(LoanApplication)).scalar() or 0
    approved_loans = db.session.execute(
        db.select(func.count()).select_from(LoanApplication).filter(LoanApplication.status == "approved")
    ).scalar() or 0
    return jsonify({
        "total_kyc": int(total_kyc),
        "verified_kyc": int(verified_kyc),
        "total_loans": int(total_loans),
        "approved_loans": int(approved_loans),
    })


@bp.get("/analytics/recent-kyc")
def analytics_recent_kyc():
    rows = db.session.execute(
        db.select(KycRecord).order_by(KycRecord.created_at.desc()).limit(10)
    ).scalars().all()
    items = []
    for r in rows:
        items.append({
            "kyc_id": r.kyc_id,
            "name": r.name,
            "status": r.status,
            "created_at": r.created_at.isoformat() + "Z" if r.created_at else "",
        })
    return jsonify({"items": items})


@bp.get("/eligible-kyc")
@limiter.limit("30/minute")
def eligible_kyc_list():
    # Users with prediction == 'eligible' and KYC status verified, with latest KYC PDF
    # Strategy: get recent verified KYC, check eligible loan for same user, attach latest KycPdf
    rows = db.session.execute(
        db.select(KycRecord).where(KycRecord.status == "verified").order_by(KycRecord.created_at.desc()).limit(200)
    ).scalars().all()
    out = []
    for k in rows:
        # latest eligible loan for this user
        la = db.session.execute(
            db.select(LoanApplication).where(LoanApplication.user_id == k.user_id, LoanApplication.prediction == 'eligible').order_by(LoanApplication.created_at.desc())
        ).scalars().first()
        if not la:
            continue
        pdf = db.session.execute(
            db.select(KycPdf).filter_by(kyc_id=k.kyc_id).order_by(KycPdf.id.desc())
        ).scalars().first()
        if not pdf:
            continue
        u = db.session.get(User, k.user_id)
        out.append({
            "kyc_id": k.kyc_id,
            "name": k.name,
            "email": (u.email if u else ""),
            "status": k.status,
            "pdf_url": f"/api/banker/kyc/{k.kyc_id}/pdf",
            "loan_id": la.id,
            "loan_prediction": la.prediction,
            "created_at": k.created_at.isoformat() + "Z" if k.created_at else "",
        })
    return jsonify({"items": out})


@bp.get("/analytics/recent-loans")
def analytics_recent_loans():
    rows = db.session.execute(
        db.select(LoanApplication).order_by(LoanApplication.created_at.desc()).limit(10)
    ).scalars().all()
    items = []
    for a in rows:
        items.append({
            "id": a.id,
            "status": a.status,
            "created_at": a.created_at.isoformat() + "Z" if a.created_at else "",
        })
    return jsonify({"items": items})


@bp.get("/applications")
def applications():
    q = db.select(LoanApplication).order_by(LoanApplication.created_at.desc())
    status = (request.args.get("status") or "").strip()
    if status:
        q = q.filter(LoanApplication.status == status)
    # Optional date filters (YYYY-MM-DD)
    dt_from = (request.args.get("from") or "").strip()
    dt_to = (request.args.get("to") or "").strip()
    # Lightweight date filtering using string compare to keep simple (SQLite)
    if dt_from:
        q = q.filter(func.date(LoanApplication.created_at) >= dt_from)
    if dt_to:
        q = q.filter(func.date(LoanApplication.created_at) <= dt_to)

    rows = db.session.execute(q.limit(200)).scalars().all()
    items = []
    for a in rows:
        u = db.session.get(User, a.user_id)
        dj = a.data_json or {}
        items.append({
            "id": a.id,
            "status": a.status,
            "created_at": a.created_at.isoformat() + "Z" if a.created_at else "",
            "full_name": (dj.get("full_name") or dj.get("name") or "").strip(),
            "email": (u.email if u else ""),
            "amount": dj.get("amount"),
            "term": dj.get("term"),
            "prediction": a.prediction,
        })
    return jsonify({"items": items})


@bp.post("/verify")
@limiter.limit("30/minute")
def verify_qr():
    data = request.get_json(silent=True) or {}
    payload = data.get("payload") or {}
    sig = (data.get("sig") or data.get("signature") or "").strip()
    kyc_id = (payload.get("kyc_id") or data.get("kyc_id") or "").strip()
    pdf_checksum = (payload.get("pdf_checksum") or data.get("pdf_checksum") or "").strip()
    issued_at = (payload.get("issued_at") or data.get("issued_at") or "").strip()
    if not kyc_id or not sig:
        return jsonify({"ok": False, "error": "Missing fields"}), 400
    # Verify signature
    expected = sign_payload({"kyc_id": kyc_id, "pdf_checksum": pdf_checksum, "issued_at": issued_at})
    if expected != sig:
        return jsonify({"ok": False, "error": "Signature mismatch"}), 400
    # Verify KYC and checksum
    kyc = db.session.execute(db.select(KycRecord).filter_by(kyc_id=kyc_id)).scalar_one_or_none()
    if not kyc:
        return jsonify({"ok": False, "error": "KYC not found"}), 404
    pdf = db.session.execute(db.select(KycPdf).filter_by(kyc_id=kyc_id)).scalar_one_or_none()
    if not pdf:
        return jsonify({"ok": False, "error": "KYC PDF not found"}), 404
    checksum_ok = (not pdf_checksum) or (pdf.pdf_checksum == pdf_checksum)
    return jsonify({
        "ok": True,
        "checksum_ok": checksum_ok,
        "kyc": {
            "kyc_id": kyc.kyc_id,
            "name": kyc.name,
            "status": kyc.status,
        },
        "pdf_checksum": pdf.pdf_checksum,
    })


# Note: summary route already defined above without the limiter; avoid duplicate definitions


@bp.get("/analytics/series")
@limiter.limit("30/minute")
def analytics_series():
    # last 14 days, per day counts
    days = 14
    today = datetime.utcnow().date()
    start = today - timedelta(days=days-1)

    def daterange(d0, d1):
        d = d0
        while d <= d1:
            yield d
            d += timedelta(days=1)

    # KYC per day
    kyc_rows = db.session.execute(
        db.select(KycRecord.created_at).where(KycRecord.created_at >= datetime.combine(start, datetime.min.time()))
    ).scalars().all()
    kyc_counts = defaultdict(int)
    for ts in kyc_rows:
        d = ts.date()
        kyc_counts[d] += 1

    # Loans per day
    loan_rows = db.session.execute(
        db.select(LoanApplication.created_at).where(LoanApplication.created_at >= datetime.combine(start, datetime.min.time()))
    ).scalars().all()
    loan_counts = defaultdict(int)
    for ts in loan_rows:
        d = ts.date()
        loan_counts[d] += 1

    series = []
    for d in daterange(start, today):
        series.append({
            "date": d.isoformat(),
            "kyc": kyc_counts.get(d, 0),
            "loans": loan_counts.get(d, 0),
        })

    return jsonify({"series": series})


@bp.get("/analytics/recent-kyc")
@limiter.limit("30/minute")
def recent_kyc():
    rows = db.session.execute(
        db.select(KycRecord).order_by(KycRecord.created_at.desc()).limit(10)
    ).scalars().all()
    out = []
    for k in rows:
        out.append({
            "kyc_id": k.kyc_id,
            "name": k.name,
            "status": k.status,
            "created_at": k.created_at.isoformat() + "Z" if k.created_at else "",
        })
    return jsonify({"items": out})


@bp.get("/applications")
@limiter.limit("30/minute")
def applications_tracker():
    # Filters: status, from (YYYY-MM-DD), to (YYYY-MM-DD)
    status = (request.args.get('status') or '').strip().lower()
    d_from = (request.args.get('from') or '').strip()
    d_to = (request.args.get('to') or '').strip()

    stmt = db.select(LoanApplication)
    if status:
        stmt = stmt.filter_by(status=status)
    # Date range on created_at
    try:
        if d_from:
            d0 = datetime.fromisoformat(d_from)
            stmt = stmt.where(LoanApplication.created_at >= d0)
        if d_to:
            # include entire day if only date provided
            if len(d_to) == 10:
                d1 = datetime.fromisoformat(d_to + 'T23:59:59')
            else:
                d1 = datetime.fromisoformat(d_to)
            stmt = stmt.where(LoanApplication.created_at <= d1)
    except Exception:
        pass

    stmt = stmt.order_by(LoanApplication.created_at.desc()).limit(100)
    rows = db.session.execute(stmt).scalars().all()
    items = []
    for a in rows:
        items.append({
            'id': a.id,
            'status': a.status,
            'created_at': a.created_at.isoformat() + 'Z' if a.created_at else '',
            'amount': (a.data_json or {}).get('amount'),
            'term': (a.data_json or {}).get('term'),
            'email': (a.data_json or {}).get('email'),
            'full_name': (a.data_json or {}).get('full_name'),
        })
    return jsonify({'items': items})


@bp.get("/analytics/recent-loans")
@limiter.limit("30/minute")
def recent_loans():
    rows = db.session.execute(
        db.select(LoanApplication).order_by(LoanApplication.created_at.desc()).limit(10)
    ).scalars().all()
    out = []
    for a in rows:
        out.append({
            "id": a.id,
            "status": a.status,
            "created_at": a.created_at.isoformat() + "Z" if a.created_at else "",
        })
    return jsonify({"items": out})


@bp.post("/kyc/qr-scan")
@limiter.limit("30/minute")
def qr_scan():
    """Handle QR code image upload and extract KYC ID"""
    try:
        if 'qr_image' not in request.files:
            return jsonify({"error": "No QR image uploaded"}), 400
        
        file = request.files['qr_image']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            return jsonify({"error": "Invalid image format"}), 400
        
        # For now, simulate QR code processing
        # In a real implementation, you would use a QR code library like pyzbar or qrcode
        filename = secure_filename(file.filename)
        temp_path = os.path.join('temp', filename)
        os.makedirs('temp', exist_ok=True)
        file.save(temp_path)
        
        # Simulate KYC ID extraction from QR code
        # In production, implement actual QR code reading here
        simulated_kyc_id = f"KYC{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Clean up temp file
        try:
            os.remove(temp_path)
        except:
            pass
        
        # Now lookup the KYC with the extracted ID
        return lookup(simulated_kyc_id)
        
    except Exception as e:
        return jsonify({"error": f"QR scan failed: {str(e)}"}), 500


@bp.post("/kyc/validate-pdf")
@limiter.limit("30/minute")
def validate_pdf():
    """Validate uploaded PDF document"""
    try:
        if 'pdf_document' not in request.files:
            return jsonify({"error": "No PDF document uploaded"}), 400
        
        file = request.files['pdf_document']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Invalid file format. Only PDF files are allowed"}), 400
        
        # Read file content
        file_content = file.read()
        file_size = len(file_content)
        
        # Calculate checksum
        checksum = hashlib.sha256(file_content).hexdigest()
        
        # Basic PDF validation
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            return jsonify({"error": "File too large. Maximum size is 10MB"}), 400
        
        if file_size < 1024:  # 1KB minimum
            return jsonify({"error": "File too small. May be corrupted"}), 400
        
        # Check PDF header
        if not file_content.startswith(b'%PDF'):
            return jsonify({"error": "Invalid PDF format"}), 400
        
        # Simulate KYC ID extraction from PDF
        # In production, implement PDF text extraction here
        simulated_kyc_id = f"KYC{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Check if this PDF exists in database
        existing_pdf = db.session.execute(
            db.select(KycPdf).filter_by(pdf_checksum=checksum).limit(1)
        ).scalars().first()
        
        issues = []
        if not existing_pdf:
            issues.append("PDF not found in database")
        
        return jsonify({
            "valid": existing_pdf is not None,
            "filename": file.filename,
            "file_size": file_size,
            "document_type": "KYC Document",
            "extracted_kyc_id": simulated_kyc_id,
            "checksum": checksum,
            "checksum_valid": existing_pdf is not None,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "issues": issues
        })
        
    except Exception as e:
        return jsonify({"error": f"PDF validation failed: {str(e)}"}), 500
