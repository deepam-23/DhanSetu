# Loan Platform (Scaffold)

A Flask-based scaffold for a loan platform with authentication, KYC onboarding, secure KYC PDF generation (stubbed), banker verification portal (stubbed), and loan draft saving.

## Quickstart

1. Create and activate a virtual environment (Windows PowerShell):
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

2. Install dependencies:
   pip install -r requirements.txt

3. Configure environment:
   copy .env.example to .env and edit values

4. Initialize folders:
   mkdir instance storage

5. Run the app:
   python run.py

The app will start on http://127.0.0.1:5000

## Endpoints (initial)
- GET / -> health/info
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/logout
- POST /api/loan/save-draft
- POST /api/kyc/start
- POST /api/kyc/finalize (stub)
- GET /api/banker/kyc/<kyc_id> (stub)

## Notes
- Database: SQLite by default (instance/app.db). Switch via DATABASE_URL.
- Secrets: Set SECRET_KEY, SERVER_SALT, SERVER_SIGNING_SECRET.
- OCR, PDF signing, storage, and chatbot integrations are skeletons to be extended.
