from fastapi.testclient import TestClient


REVISION = "0123456789abcdef0123456789abcdef01234567"


def client_for_revision(monkeypatch):
    monkeypatch.setenv("APP_REVISION", REVISION)
    from app.main import create_app

    return TestClient(create_app())


def test_health_identifies_the_running_commit(monkeypatch):
    with client_for_revision(monkeypatch) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "revision": REVISION}


def test_version_identifies_the_running_commit(monkeypatch):
    with client_for_revision(monkeypatch) as client:
        response = client.get("/version")
        assert response.status_code == 200
        assert response.json() == {"version": REVISION}


def test_openapi_exposes_the_running_version_and_health_contract(monkeypatch):
    with client_for_revision(monkeypatch) as client:
        schema = client.get("/openapi.json").json()
        assert schema["info"]["version"] == REVISION
        assert "/health" in schema["paths"]
        assert "/version" in schema["paths"]
