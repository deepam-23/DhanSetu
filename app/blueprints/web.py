from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from flask_login import current_user, login_required
from ..extensions import csrf

bp = Blueprint("web", __name__)


@bp.get("/")
def home():
    return render_template("index.html")


@bp.get("/login")
def login_page():
    return render_template("auth_login.html")


@bp.get("/register")
def register_page():
    return render_template("auth_register.html")


@bp.get("/banker-login")
def banker_login_page():
    return render_template("banker_login.html")


@bp.get("/banker-dashboard")
def banker_dashboard_page():
    return render_template("banker_dashboard.html")


@bp.get("/loan")
@login_required
def loan_page():
    return render_template("loan_form.html")


@bp.get("/kyc")
@login_required
def kyc_page():
    return render_template("kyc.html")




@bp.get("/chat")
def chat_page():
    return render_template("chat.html")


@bp.get("/user-dashboard")
@login_required
def user_dashboard():
    return render_template("user_dashboard.html")




@csrf.exempt
@bp.post("/api/chat")
def chat_api():
    try:
        data = request.get_json(silent=True) or {}
        msg = (data.get("message") or "").strip().lower()
        lang = (data.get("lang") or "en").lower()
        if not msg:
            text_en = "Hello! Ask me about loans, KYC, eligibility, documents, or interest rates."
            text_kn = "ನಮಸ್ಕಾರ! ಸಾಲ, KYC, ಅರ್ಹತೆ, ದಾಖಲೆಗಳು ಅಥವಾ ಬಡ್ಡಿದರಗಳ ಬಗ್ಗೆ ಕೇಳಿ."
            return jsonify({"reply": text_kn if lang.startswith("kn") else text_en})

        def r(text_en, text_kn=None):
            if text_kn is None:
                text_kn = text_en
            return jsonify({"reply": (text_kn if lang.startswith("kn") else text_en)})

        if any(k in msg for k in ["hi", "hello", "hey", "namaste", "good morning", "good evening", "good afternoon"]):
            return r(
                "Hello! I’m your DhanSetu assistant. I can help with interest rates, documents, KYC steps, eligibility and how to apply. How can I help?",
                "ನಮಸ್ಕಾರ! ನಾನು ಧನ್‌ಸೇತು ಸಹಾಯಕ. ಬಡ್ಡಿದರ, ದಾಖಲೆಗಳು, KYC ಹಂತಗಳು, ಅರ್ಹತೆ ಹಾಗೂ ಅರ್ಜಿ ಸಲ್ಲಿಸುವ ಕ್ರಮದಲ್ಲಿ ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
            )

        if any(k in msg for k in ["rate", "interest", "apr"]):
            return r(
                "Our personal loan APR typically ranges from 12%-18% depending on profile. Use the eligibility tool on the Loan page for a quick check.",
                "ನಮ್ಮ ವೈಯಕ್ತಿಕ ಸಾಲದ APR ಸಾಮಾನ್ಯವಾಗಿ 12%-18% ನಡುವೆ ಇರುತ್ತದೆ (ನಿಮ್ಮ ಪ್ರೊಫೈಲ್ ಆಧಾರಿತ). ತ್ವರಿತ ಪರಿಶೀಲನೆಗಾಗಿ Loan ಪುಟದಲ್ಲಿರುವ ಅರ್ಹತೆ ಸಾಧನವನ್ನು ಬಳಸಿ.",
            )
        if any(k in msg for k in ["document", "docs", "kyc doc", "kyc documents"]):
            return r(
                "Basic KYC requires a government ID (Aadhaar/PAN/Passport), address proof, and DOB. Submit via the KYC page; a PDF is generated with a secure checksum.",
                "ಮೂಲ KYC ಗೆ ಸರ್ಕಾರದ ID (ಆಧಾರ್/ಪಾನ್/ಪಾಸ್ಪೋರ್ಟ್), ವಿಳಾಸ ಪ್ರಮಾಣಪತ್ರ ಮತ್ತು ಜನ್ಮ ದಿನಾಂಕ ಅಗತ್ಯ. KYC ಪುಟದಲ್ಲಿ ಸಲ್ಲಿಸಿ; ಸುರಕ್ಷಿತ ಚೆಕ್ಸಮ್‌ನೊಂದಿಗೆ PDF ನಿರ್ಮಿಸಲಾಗುತ್ತದೆ.",
            )
        if any(k in msg for k in ["kyc", "verify", "verification"]):
            return r(
                "Start KYC on the KYC page. After you finalize, a KYC ID is generated and sent to the banker dashboard for authentication.",
                "KYC ಪುಟದಲ್ಲಿ ಪ್ರಾರಂಭಿಸಿ. ಫೈನಲೈಸ್ ಮಾಡಿದ ನಂತರ KYC ID ರಚಿಸಿ ಬ್ಯಾಂಕರ್ ಡ್ಯಾಶ್‌ಬೋರ್ಡ್‌ಗೆ ಪ್ರಮಾಣೀಕರಣಕ್ಕಾಗಿ ಕಳುಹಿಸಲಾಗುತ್ತದೆ.",
            )
        if any(k in msg for k in ["eligibility", "eligible", "emi", "calculate"]):
            return r(
                "Use the Loan page to estimate EMI and eligibility. Enter amount, term, and income; we compare your capacity vs required EMI.",
                "EMI ಮತ್ತು ಅರ್ಹತೆಯನ್ನು ಅಂದಾಜಿಸಲು Loan ಪುಟವನ್ನು ಬಳಸಿ. ಮೊತ್ತ, ಅವಧಿ ಮತ್ತು ಆದಾಯವನ್ನು ನಮೂದಿಸಿ; ಅಗತ್ಯ EMI ಗೆ ನಿಮ್ಮ ಸಾಮರ್ಥ್ಯವನ್ನು ಹೋಲಿಸುತ್ತೇವೆ.",
            )
        if any(k in msg for k in ["apply", "loan", "how to"]):
            return r(
                "Go to the Loan page to start an application. Save a draft, then complete KYC to proceed for banker review.",
                "ಅರ್ಜಿಯನ್ನು ಪ್ರಾರಂಭಿಸಲು Loan ಪುಟಕ್ಕೆ ಹೋಗಿ. ಮೊದಲು ಡ್ರಾಫ್ಟ್ ಉಳಿಸಿ, ನಂತರ ಬ್ಯಾಂಕರ್ ಪರಿಶೀಲನೆಗೆ ಮುಂದಾಗಲು KYC ಪೂರ್ಣಗೊಳಿಸಿ.",
            )

        return r(
            "I can help with: interest rates, required documents, KYC steps, eligibility, and how to apply. How can I assist?",
            "ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲ ವಿಷಯಗಳು: ಬಡ್ಡಿದರಗಳು, ಅಗತ್ಯ ದಾಖಲೆಗಳು, KYC ಹಂತಗಳು, ಅರ್ಹತೆ ಹಾಗೂ ಅರ್ಜಿ ಸಲ್ಲಿಸುವ ವಿಧಾನ. ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
        )
    except Exception:
        return jsonify({"reply": "Sorry, I had trouble processing that. Please try again."}), 200
