"""CardCue backend application."""

from fastapi import FastAPI

from cardcue_api.api.billing import router as billing_router
from cardcue_api.api.devices import router as devices_router
from cardcue_api.api.sync import router as sync_router
from cardcue_api.api.mail import router as mail_router
from cardcue_api.api.drafts import router as drafts_router

app = FastAPI(title="CardCue", version="0.4.0")

app.include_router(billing_router)
app.include_router(devices_router)
app.include_router(sync_router)
app.include_router(mail_router)
app.include_router(drafts_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cardcue", "version": "0.4.0"}


@app.get("/v1/capabilities")
def capabilities() -> dict[str, bool | str]:
    return {
        "stage": "s4-parsing-drafts",
        "accounts": True,
        "statements": True,
        "payments": True,
        "device_auth": True,
        "sync": True,
        "email_sync": True,
        "statement_parsing": True,
        "payment_execution": False,
    }
