import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate

from .config import config_by_name
from .extensions import db
from .routes import api


def create_app(test_config=None):
    app = Flask(__name__)
    config_name = os.getenv("APP_ENV", "development")
    app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    Migrate(app, db)
    JWTManager(app)

    allowed_origins = [origin.strip() for origin in app.config.get("FRONTEND_ORIGIN", "").split(",") if origin.strip()]
    CORS(
        app,
        resources={r"/api/*": {"origins": allowed_origins if allowed_origins else "*"}},
        supports_credentials=False,
    )
    app.register_blueprint(api, url_prefix="/api")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "safedrop-api"})

    with app.app_context():
        db.create_all()
    return app
