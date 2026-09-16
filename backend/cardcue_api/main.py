"""Phase-one service skeleton. No credentials or email content are accepted yet."""

from fastapi import FastAPI

app = FastAPI(title="CardCue", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cardcue", "version": "0.1.0"}


@app.get("/v1/capabilities")
def capabilities() -> dict[str, bool | str]:
    return {
        "stage": "local-demo",
        "email_sync": False,
        "statement_parsing": False,
        "payment_execution": False,
    }
