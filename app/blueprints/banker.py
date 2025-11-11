import json
from flask import Blueprint, jsonify, request, send_file
from datetime import datetime, timedelta
from collections import defaultdict
from flask import session
from ..extensions import db, limiter
from ..models import KycRecord, KycPdf, LoanApplication
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


@bp.get("/kyc/<string:kyc_id>/pdf")
@limiter.limit("10/minute")
def download_pdf(kyc_id: str):
    pdf = db.session.execute(db.select(KycPdf).filter_by(kyc_id=kyc_id)).scalar_one_or_none()
    if not pdf:
        return jsonify({"error": "KYC PDF not found"}), 404
    return send_file(pdf.pdf_url, mimetype="application/pdf")


@bp.get("/analytics/summary")
@limiter.limit("30/minute")
def analytics_summary():
    total_kyc = db.session.execute(db.select(db.func.count()).select_from(KycRecord)).scalar()
    verified_kyc = db.session.execute(db.select(db.func.count()).select_from(KycRecord).filter_by(status="verified")).scalar()
    total_loans = db.session.execute(db.select(db.func.count()).select_from(LoanApplication)).scalar()
    approved_loans = db.session.execute(db.select(db.func.count()).select_from(LoanApplication).filter_by(status="approved")).scalar()
    return jsonify({
        "total_kyc": total_kyc or 0,
        "verified_kyc": verified_kyc or 0,
        "total_loans": total_loans or 0,
        "approved_loans": approved_loans or 0,
    })


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
