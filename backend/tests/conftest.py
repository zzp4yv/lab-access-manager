from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("PROVISIONING_MODE", "dry_run")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("UPLOAD_DIR", "/tmp/lab-access-manager-test-uploads")
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Admin
from app.security import hash_password


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_token(db_session, client):
    admin = Admin(
        full_name="Admin de Teste",
        email="admin@oxigenioaceleradora.com.br",
        hashed_password=hash_password("SenhaForte123!"),
    )
    db_session.add(admin)
    db_session.commit()

    resp = client.post(
        "/api/auth/login",
        json={"email": admin.email, "password": "SenhaForte123!"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture()
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
