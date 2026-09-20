import uuid
import pytest
from sqlalchemy import select
from cardcue_api.config import settings
from cardcue_api.admin.models import ModelProfile, ModelRevision, RuntimeSettings
from cardcue_api.admin.config_api import ensure_default_model_from_env
from cardcue_api.services.drafts import DraftService
from cardcue_api.persistence.database import async_session_factory

@pytest.mark.asyncio
async def test_ensure_default_model_and_draft_fallback():
    async with async_session_factory() as session:
        # Check if ensure_default_model_from_env works
        await ensure_default_model_from_env(session)
        state = await session.get(RuntimeSettings, "model")
        assert state is not None
        assert "revision_id" in state.value
        active_rev_id = uuid.UUID(state.value["revision_id"])
        rev = await session.get(ModelRevision, active_rev_id)
        assert rev is not None
        assert rev.parameters["model"] == settings.llm_model

    # Check DraftService initial state
    service = DraftService()
    assert service.model_extractor.revision is None