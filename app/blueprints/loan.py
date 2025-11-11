from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from ..extensions import db
from ..models import LoanApplication

bp = Blueprint("loan", __name__)


@bp.post("/save-draft")
@login_required
def save_draft():
    payload = request.get_json() or {}
    app_id = payload.get("id")

    if app_id:
        loan = db.session.get(LoanApplication, int(app_id))
        if not loan or loan.user_id != current_user.id:
            return jsonify({"error": "Not found"}), 404
    else:
        loan = LoanApplication(user_id=current_user.id)
        db.session.add(loan)

    loan.data_json = payload.get("data") or {}
    loan.status = "draft"
    db.session.commit()

    return jsonify({"id": loan.id, "status": loan.status, "data": loan.data_json})


@bp.get("/my")
@login_required
def my_loans():
    rows = db.session.execute(
        db.select(LoanApplication)
        .filter_by(user_id=current_user.id)
        .order_by(LoanApplication.created_at.desc())
    ).scalars().all()
    out = []
    for a in rows:
        out.append({
            "id": a.id,
            "status": a.status,
            "created_at": a.created_at.isoformat() + "Z" if a.created_at else "",
            "amount": (a.data_json or {}).get("amount"),
            "term": (a.data_json or {}).get("term"),
            "purpose": (a.data_json or {}).get("purpose"),
        })
    return jsonify({"items": out})
