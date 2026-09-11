import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_rauzr.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_demo_booking_public_no_auth_required():
    payload = {
        "full_name": "Jordan Rivera",
        "work_email": "jordan@example-pharma.com",
        "company": "Example Pharma Inc.",
        "role": "Head of Regulatory Affairs",
        "team_size": "11-50",
        "message": "Interested in the GxP audit workflow.",
    }
    resp = client.post("/api/demo-bookings", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["work_email"] == payload["work_email"]
    assert body["status"] == "pending"


def test_demo_booking_honeypot_silently_drops():
    payload = {
        "full_name": "Bot",
        "work_email": "bot@example.com",
        "company": "Bot Co",
        "website": "http://spam.example",  # honeypot filled -> rejected
    }
    resp = client.post("/api/demo-bookings", json=payload)
    assert resp.status_code == 201
    assert resp.json() is None


def test_demo_booking_rejects_invalid_email():
    resp = client.post(
        "/api/demo-bookings",
        json={"full_name": "A", "work_email": "not-an-email", "company": "X"},
    )
    assert resp.status_code == 422


def test_register_and_login_flow():
    email = "founder@rauzr-example.com"
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Founder", "password": "StrongPassw0rd!"},
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == email

    # Wrong password -> generic 401, no user enumeration
    resp = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
    assert resp.status_code == 401


def test_run_bundled_sample_pipeline():
    resp = client.post("/api/pipeline/run-sample")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["compliance_score"] is not None
    assert body["report"]["summary"]["total_rules"] > 0


def test_run_pipeline_rejects_non_pdf():
    resp = client.post(
        "/api/pipeline/run",
        files={
            "dossier": ("dossier.txt", b"not a pdf", "text/plain"),
            "qa_package": ("qa.pdf", b"%PDF-1.4 fake", "application/pdf"),
        },
    )
    assert resp.status_code == 415
