from fastapi.testclient import TestClient
from cardcue_api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "cardcue"


def test_unimplemented_capabilities_are_explicit():
    data = client.get("/v1/capabilities").json()
    assert data["email_sync"] is False
    assert data["statement_parsing"] is False
    assert data["payment_execution"] is False


def test_no_pretend_parser():
    assert client.post("/v1/parse", json={"body": "sample"}).status_code == 404
