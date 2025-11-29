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
    # Compute simple eligibility and store in prediction
    try:
        d = loan.data_json or {}
        amount = float(d.get("amount") or 0)
        term = int(d.get("term") or 0)
        income = float(d.get("income") or 0)
        emi_existing = float(d.get("emi") or 0)
        credit = float(d.get("credit_score") or 0)
        age = int(d.get("age") or 0)
        emp = str(d.get("employment_type") or '').lower()
        res = str(d.get("residence_type") or '').lower()

        annual_rate = 0.14
        r = annual_rate/12.0
        emi_needed = int(round((amount*r*(1+r)**term)/(((1+r)**term-1) if term>0 else 1))) if term>0 and amount>0 else 0

        capacity = max(0.0, income - emi_existing)
        boost = 0.0
        
        # Age-based eligibility factors
        if age < 21:
            boost -= 0.10  # Penalty for very young applicants
        elif age < 25:
            boost -= 0.05  # Small penalty for young adults
        elif age >= 21 and age <= 60:
            if age >= 25 and age <= 45:
                boost += 0.08  # Prime age bracket
            elif age > 45 and age <= 55:
                boost += 0.05  # Good age bracket
            elif age > 55 and age <= 60:
                boost += 0.02  # Acceptable age bracket
        else:
            boost -= 0.15  # Penalty for applicants over 60 (retirement risk)
            
        # Credit score factors
        if credit >= 800: boost += 0.12
        elif credit >= 750: boost += 0.08
        elif credit >= 700: boost += 0.04
        
        # Employment factors
        if emp == 'salaried': boost += 0.05
        elif emp == 'self_employed': boost += 0.02
        elif emp == 'student': boost -= 0.10
        elif emp == 'retired': boost -= 0.05
        
        # Residence factors
        if res == 'owned': boost += 0.03
        elif res == 'parental': boost += 0.01
        
        boosted_capacity = int(round(capacity * (1 + boost)))

        eligible = (boosted_capacity >= emi_needed and amount>0 and term>0 and age >= 21 and age <= 60)
        loan.prediction = 'eligible' if eligible else 'ineligible'
    except Exception:
        # If parsing fails, leave prediction unchanged
        pass
    db.session.commit()

    return jsonify({"id": loan.id, "status": loan.status, "data": loan.data_json, "prediction": loan.prediction})


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
            "prediction": a.prediction,
        })
    return jsonify({"items": out})
