from fastapi.testclient import TestClient
from cardcue_api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "cardcue"
    assert response.json()["version"] == "0.5.0"


def test_capabilities_r1():
    data = client.get("/v1/capabilities").json()
    assert data["stage"] == "r1-delivery"
    assert data["accounts"] is True
    assert data["statements"] is True
    assert data["payments"] is True
    assert data["device_auth"] is True
    assert data["email_sync"] is True
    assert data["statement_parsing"] is True
    assert data["backup_restore"] is True
    assert data["payment_execution"] is False


def test_no_pretend_parser():
    assert client.post("/v1/parse", json={"body": "sample"}).status_code in (404, 405)
