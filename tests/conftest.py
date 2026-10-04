# Author: Yogesh Agrawal
"""Shared pytest fixtures.

Each test session gets isolated temporary SQLite databases and seeded data,
so tests never touch real data and are deterministic.
"""
import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("data")
    os.environ["BANK_DB"] = str(tmp / "bank.db")
    os.environ["SESSIONS_DB"] = str(tmp / "sessions.db")
    os.environ["DATA_DIR"] = str(tmp)
    os.environ["MOCK_BANK_URL"] = "http://127.0.0.1:9100"
    os.environ["PII_ENABLED"] = "true"
    os.environ["PII_SPACY_MODEL"] = "en_core_web_sm"
    os.environ["LANGFUSE_ENABLED"] = "false"
    os.environ["JWT_SECRET"] = "test-secret"

    # Clear cached settings so the new env is picked up.
    from app.config import get_settings
    get_settings.cache_clear()

    # Initialize + seed databases.
    from mock_bank import seed
    seed.main()
    yield
