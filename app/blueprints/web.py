from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from flask_login import current_user
from ..extensions import csrf

bp = Blueprint("web", __name__)


@bp.get("/")
def home():
    return render_template("dashboard.html", user=current_user if current_user.is_authenticated else None)


@bp.get("/login")
def login_page():
    return render_template("auth_login.html")


@bp.get("/register")
def register_page():
    return render_template("auth_register.html")


@bp.get("/loan")
def loan_page():
    return render_template("loan_form.html")


@bp.get("/kyc")
def kyc_page():
    return render_template("kyc.html")


@bp.get("/banker")
def banker_page():
    return render_template("banker_lookup.html")

@bp.get("/chat")
def chat_page():
    return render_template("chat.html")

@bp.get("/user-dashboard")
def user_dashboard():
    return render_template("user_dashboard.html")


@bp.get("/banker-dashboard")
def banker_dashboard():
    if not session.get("banker_id"):
        return redirect(url_for("web.banker_login_page"))
    return render_template("banker_dashboard.html")


@bp.get("/banker-login")
def banker_login_page():
    return render_template("banker_login.html")


@csrf.exempt
@bp.post("/api/chat")
def chat_api():
    try:
        data = request.get_json(silent=True) or {}
        msg = (data.get("message") or "").strip().lower()
        if not msg:
            return jsonify({"reply": "Hello! Ask me about loans, KYC, eligibility, documents, or interest rates."})

        def r(text):
            return jsonify({"reply": text})

        if any(k in msg for k in ["hi", "hello", "hey", "namaste", "good morning", "good evening", "good afternoon"]):
            return r("Hello! I’m your DhanSetu assistant. I can help with interest rates, documents, KYC steps, eligibility and how to apply. How can I help?")

        if any(k in msg for k in ["rate", "interest", "apr"]):
            return r("Our example personal loan APR typically ranges from 12%-18% depending on profile. Use the eligibility tool on the Loan page for a quick check.")
        if any(k in msg for k in ["document", "docs", "kyc doc", "kyc documents"]):
            return r("Basic KYC requires a government ID (Aadhaar/PAN/Passport), address proof, and DOB. Submit via the KYC page; a PDF is generated with a secure checksum.")
        if any(k in msg for k in ["kyc", "verify", "verification"]):
            return r("Start KYC on the KYC page. After you finalize, a KYC ID is generated and sent to the banker dashboard for authentication.")
        if any(k in msg for k in ["eligibility", "eligible", "emi", "calculate"]):
            return r("Use the Loan page to estimate EMI and eligibility. Enter amount, term, and income; we compare your capacity vs required EMI.")
        if any(k in msg for k in ["apply", "loan", "how to"]):
            return r("Go to the Loan page to start an application. Save a draft, then complete KYC to proceed for banker review.")

        return r("I can help with: interest rates, required documents, KYC steps, eligibility, and how to apply. How can I assist?")
    except Exception:
        return jsonify({"reply": "Sorry, I had trouble processing that. Please try again."}), 200
