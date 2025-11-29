import os
from flask import Flask, jsonify
from .extensions import db, login_manager, csrf, limiter
from .config import Config
from .models import User


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    # Ensure instance and storage directories
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config.get("STORAGE_DIR", "storage"), exist_ok=True)

    # Normalize SQLite path to an absolute file under instance/ to avoid Windows path issues
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if db_uri.startswith("sqlite:///") and ("instance/" in db_uri or "instance\\" in db_uri):
        db_path = os.path.join(app.instance_path, "app.db")
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

    # Init extensions
    db.init_app(app)
    login_manager.init_app(app)
    # Redirect unauthenticated users to the login page for protected views
    login_manager.login_view = 'web.login_page'
    login_manager.login_message_category = 'info'
    csrf.init_app(app)
    limiter.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Blueprints
    from .blueprints.auth import bp as auth_bp
    from .blueprints.loan import bp as loan_bp
    from .blueprints.kyc import bp as kyc_bp
    from .blueprints.web import bp as web_bp
    from .blueprints.banker import bp as banker_bp

    # Exempt API blueprints from CSRF (using JSON and token-based/session auth)
    csrf.exempt(auth_bp)
    csrf.exempt(loan_bp)
    csrf.exempt(kyc_bp)
    csrf.exempt(banker_bp)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(loan_bp, url_prefix="/api/loan")
    app.register_blueprint(kyc_bp, url_prefix="/api/kyc")
    app.register_blueprint(web_bp)
    app.register_blueprint(banker_bp, url_prefix="/api/banker")

    @app.get("/api")
    def api_index():
        return jsonify({
            "name": "loan-platform",
            "status": "ok",
            "endpoints": [
                "/api/auth/register", "/api/auth/login", "/api/auth/logout",
                "/api/loan/save-draft", "/api/loan/my", "/api/kyc/start", "/api/kyc/finalize", "/api/kyc/me", "/api/kyc/me/pdf",
                "/api/banker/kyc/<kyc_id>", "/api/banker/kyc/qr-scan", "/api/banker/kyc/validate-pdf", "/api/banker/analytics/summary"
            ]
        })

    @app.context_processor
    def inject_ctx():
        from flask import session as _s
        return {
            "banker": {
                "id": _s.get("banker_id"),
                "email": _s.get("banker_email"),
                "role": _s.get("banker_role"),
            }
        }

    with app.app_context():
        db.create_all()

    return app
