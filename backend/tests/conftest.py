import pytest
from safedrop import create_app
from safedrop.extensions import db

@pytest.fixture()
def app(tmp_path):
    upload_dir = tmp_path / "uploads"
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "UPLOAD_FOLDER": str(upload_dir),
                      "JWT_SECRET_KEY": "test-jwt-secret", "FRONTEND_ORIGIN": "http://localhost:8080",
                      "MAX_CONTENT_LENGTH": 1024 * 1024})
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture()
def client(app):
    return app.test_client()

@pytest.fixture()
def auth_header(client):
    client.post("/api/auth/register", json={"email": "student@example.com", "password": "correct-horse-123"})
    response = client.post("/api/auth/login", json={"email": "student@example.com", "password": "correct-horse-123"})
    return {"Authorization": "Bearer " + response.json["access_token"]}
