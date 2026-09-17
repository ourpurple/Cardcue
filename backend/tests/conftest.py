"""Shared fixtures for async integration tests.

Session-scoped event loop (configured in pyproject.toml) ensures the
module-level asyncpg engine can reuse connections across all tests.
"""

import pytest
from cardcue_api.persistence.database import engine


@pytest.fixture(autouse=True, scope="session")
async def _dispose_engine():
    """Dispose the async engine after all tests finish."""
    yield
    await engine.dispose()
