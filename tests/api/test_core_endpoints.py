"""
Tests for core endpoints (health, config, etc.).
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check endpoint."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data or data.get("ok") is True


class TestRootEndpoint:
    """Tests for GET / endpoint."""

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        """Test root endpoint."""
        response = await client.get("/")

        assert response.status_code == 200


class TestDocsEndpoint:
    """Tests for documentation endpoints."""

    @pytest.mark.asyncio
    async def test_swagger_docs(self, client: AsyncClient):
        """Test Swagger UI endpoint."""
        response = await client.get("/api/v1/docs")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_redoc(self, client: AsyncClient):
        """Test ReDoc endpoint."""
        response = await client.get("/api/v1/redoc")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_openapi_json(self, client: AsyncClient):
        """Test OpenAPI JSON endpoint."""
        response = await client.get("/api/v1/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data


class TestFAQEndpoints:
    """Tests for FAQ endpoints."""

    @pytest.mark.asyncio
    async def test_get_faqs_public(self, client: AsyncClient):
        """Test getting public FAQs."""
        with patch(
            "app.api.api_v1.endpoints.core.get_faqs_public_cached",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = []

            response = await client.get("/api/v1/faqs/public")

            assert response.status_code == 200


class TestVersionEndpoints:
    """Tests for version check endpoints."""

    @pytest.mark.asyncio
    async def test_check_for_updates(self, client: AsyncClient):
        """Test checking for app updates."""
        with patch(
            "app.api.api_v1.endpoints.core.check_for_updates_cached",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.return_value = {
                "update_available": False,
                "latest_version": "1.0.0",
                "force_update": False,
            }

            response = await client.post(
                "/api/v1/versions/check",
                json={
                    "app": "360ghar",
                    "platform": "android",
                    "current_version": "1.0.0",
                },
            )

            assert response.status_code == 200
