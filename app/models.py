from datetime import datetime
from flask_login import UserMixin
from .extensions import db


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    email_verified_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class LoanApplication(db.Model):
    __tablename__ = "loan_applications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    data_json = db.Column(db.JSON)
    status = db.Column(db.String(20), default="draft")
    prediction = db.Column(db.String(20))
    finalized_pdf_url = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class KycRecord(db.Model):
    __tablename__ = "kyc_records"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    kyc_id = db.Column(db.String(64), unique=True)
    status = db.Column(db.String(20), default="pending")
    name = db.Column(db.String(120))
    dob = db.Column(db.String(20))
    gov_id_type = db.Column(db.String(30))
    gov_id_last4 = db.Column(db.String(8))
    address = db.Column(db.Text)
    selfie_ref = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime)


class KycPdf(db.Model):
    __tablename__ = "kyc_pdf"
    id = db.Column(db.Integer, primary_key=True)
    kyc_id = db.Column(db.String(64), db.ForeignKey("kyc_records.kyc_id"), nullable=False)
    pdf_url = db.Column(db.String(512))
    pdf_checksum = db.Column(db.String(128))
    qr_payload_hash = db.Column(db.String(128))
    signed_at = db.Column(db.DateTime, default=datetime.utcnow)


class BankerUser(db.Model):
    __tablename__ = "banker_users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default="banker")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AccessLog(db.Model):
    __tablename__ = "access_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor = db.Column(db.String(20))
    actor_id = db.Column(db.Integer)
    resource_type = db.Column(db.String(20))
    resource_id = db.Column(db.String(64))
    action = db.Column(db.String(20))
    ip = db.Column(db.String(64))
    ts = db.Column(db.DateTime, default=datetime.utcnow)
