from flask import Blueprint, request, jsonify, session
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from email_validator import validate_email, EmailNotValidError
from ..extensions import db, limiter
from ..models import User, BankerUser

bp = Blueprint("auth", __name__)


@bp.post("/register")
@limiter.limit("5/minute")
def register():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = data.get("name")

    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        return jsonify({"error": "Invalid email format"}), 400

    if not password or len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    if db.session.execute(db.select(User).filter_by(email=email)).scalar_one_or_none():
        return jsonify({"error": "Email already registered"}), 400

    user = User(email=email, name=name, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Registered successfully"}), 201


@bp.post("/login")
@limiter.limit("10/minute")
def login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = db.session.execute(db.select(User).filter_by(email=email)).scalar_one_or_none()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    login_user(user)
    return jsonify({"message": "Logged in"})


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out"})


@bp.post("/banker/login")
def banker_login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    banker = db.session.execute(db.select(BankerUser).filter_by(email=email)).scalar_one_or_none()
    if not banker or not check_password_hash(banker.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    session["banker_id"] = banker.id
    session["banker_email"] = banker.email
    session["banker_role"] = banker.role
    return jsonify({"message": "Logged in", "role": banker.role})


@bp.post("/banker/logout")
def banker_logout():
    session.pop("banker_id", None)
    session.pop("banker_email", None)
    session.pop("banker_role", None)
    return jsonify({"message": "Logged out"})


@bp.post("/banker/register")
@limiter.limit("5/minute")
def banker_register():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        return jsonify({"error": "Invalid email format"}), 400

    if not password or len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    exists = db.session.execute(db.select(BankerUser).filter_by(email=email)).scalar_one_or_none()
    if exists:
        return jsonify({"error": "Email already registered"}), 400

    banker = BankerUser(email=email, password_hash=generate_password_hash(password), role="banker")
    db.session.add(banker)
    db.session.commit()
    return jsonify({"message": "Banker registered"}), 201
