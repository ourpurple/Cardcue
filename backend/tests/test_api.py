from fastapi.testclient import TestClient
from cardcue_api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "cardcue"
    assert response.json()["version"] == "0.2.0"


def test_capabilities_s1():
    data = client.get("/v1/capabilities").json()
    assert data["stage"] == "s1-storage"
    assert data["accounts"] is True
    assert data["statements"] is True
    assert data["payments"] is True
    assert data["device_auth"] is True
    assert data["email_sync"] is False
    assert data["statement_parsing"] is False
    assert data["payment_execution"] is False


def test_no_pretend_parser():
    assert client.post("/v1/parse", json={"body": "sample"}).status_code in (404, 405)
