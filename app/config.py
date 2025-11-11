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
