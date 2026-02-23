from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_db():
    """Fluent Supabase mock — every builder method returns self, .execute() is configurable."""
    mock = MagicMock()
    for method in [
        "table", "select", "insert", "update", "delete", "rpc",
        "eq", "neq", "or_", "in_", "gte", "lte", "order", "limit", "single",
    ]:
        getattr(mock, method).return_value = mock
    return mock


@pytest.fixture(autouse=True)
def patch_db(mock_db, monkeypatch):
    monkeypatch.setattr("db._client", mock_db)
    return mock_db
