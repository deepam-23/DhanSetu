import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///instance/app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
    SERVER_SALT = os.getenv("SERVER_SALT", "change-me")
    SERVER_SIGNING_SECRET = os.getenv("SERVER_SIGNING_SECRET", "change-me")
    WTF_CSRF_TIME_LIMIT = None
    # SMTP settings for email OTP
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    FROM_EMAIL = os.getenv("FROM_EMAIL", "no-reply@example.com")
    SMTP_TLS = os.getenv("SMTP_TLS", "true").lower() in ("1", "true", "yes")
