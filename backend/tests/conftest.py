"""Shared fixtures for async integration tests.

Session-scoped event loop (configured in pyproject.toml) ensures the
module-level asyncpg engine can reuse connections across all tests.
"""

import pytest
from cardcue_api.persistence.database import engine


@pytest.fixture(autouse=True, scope="function")
async def _clear_pool():
    """Dispose stale connections before each test to avoid asyncpg conflicts."""
    await engine.dispose()
    yield
    await engine.dispose()
