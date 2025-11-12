import json
from flask import Blueprint, jsonify, request, send_file
from datetime import datetime, timedelta
from collections import defaultdict
from flask import session
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
            kyc = db.session.execute(db.select(KycRecord).filter_by(id=int(norm_id))).scalar_one_or_none()
            if kyc and kyc.kyc_id:
                norm_id = kyc.kyc_id
        if kyc is None:
            kyc = db.session.execute(db.select(KycRecord).filter_by(kyc_id=norm_id)).scalar_one_or_none()
        if not kyc:
            return jsonify({"error": "KYC not found"}), 404
        pdf = db.session.execute(db.select(KycPdf).filter_by(kyc_id=norm_id)).scalar_one_or_none()
        if not pdf:
            return jsonify({"error": "KYC PDF not found"}), 404

        payload = {"kyc_id": kyc.kyc_id, "issued_at": kyc.verified_at.isoformat() + "Z" if kyc.verified_at else "", "pdf_checksum": pdf.pdf_checksum}
        sig = sign_payload(payload)

        return jsonify({
            "kyc_id": kyc.kyc_id,
            "name": kyc.name,
            "dob": kyc.dob,
            "status": kyc.status,
            "pdf_checksum": pdf.pdf_checksum,
            "verification_signature": sig
        })
    except Exception as e:
        return jsonify({"error": f"Lookup failed: {str(e) or 'unknown'}"}), 400


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


@bp.get("/kyc/<string:kyc_id>/pdf")
@limiter.limit("10/minute")
def download_pdf(kyc_id: str):
    pdf = db.session.execute(db.select(KycPdf).filter_by(kyc_id=kyc_id)).scalar_one_or_none()
    if not pdf:
        return jsonify({"error": "KYC PDF not found"}), 404
    return send_file(pdf.pdf_url, mimetype="application/pdf")


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
