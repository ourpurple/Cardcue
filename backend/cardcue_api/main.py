"""CardCue backend application."""

from fastapi import FastAPI

from cardcue_api.api.billing import router as billing_router
from cardcue_api.api.devices import router as devices_router

app = FastAPI(title="CardCue", version="0.2.0")

app.include_router(billing_router)
app.include_router(devices_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cardcue", "version": "0.2.0"}


@app.get("/v1/capabilities")
def capabilities() -> dict[str, bool | str]:
    return {
        "stage": "s1-storage",
        "accounts": True,
        "statements": True,
        "payments": True,
        "device_auth": True,
        "email_sync": False,
        "statement_parsing": False,
        "payment_execution": False,
    }
