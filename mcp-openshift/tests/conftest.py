"""Pytest configuration and shared fixtures."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI test client for REST endpoints."""
    from main import app

    return TestClient(app)


@pytest.fixture
def mock_kubernetes():
    """Mock Kubernetes API client."""
    with (
        patch("main.core_v1"),
        patch("main.apps_v1"),
        patch("main.batch_v1"),
        patch("main.custom_objects"),
    ):
        yield


@pytest.fixture
def auth_headers():
    """Valid authentication headers."""
    return {"Authorization": "Bearer test-token-12345678901234567890123456789012"}


@pytest.fixture
def invalid_auth_headers():
    """Invalid authentication headers."""
    return {"Authorization": "Bearer invalid-token"}
