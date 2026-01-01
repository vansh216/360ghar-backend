"""
Tests for amenity endpoints.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


class TestListAmenitiesEndpoint:
    """Tests for GET /api/v1/amenities/ endpoint."""

    @pytest.mark.asyncio
    async def test_list_amenities(self, client: AsyncClient):
        """Test listing all amenities."""
        with patch(
            "app.services.property.get_all_amenities",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = [
                {"id": 1, "title": "WiFi", "icon": "wifi"},
                {"id": 2, "title": "Parking", "icon": "car"},
                {"id": 3, "title": "Pool", "icon": "pool"},
            ]

            response = await client.get("/api/v1/amenities/")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_amenities_empty(self, client: AsyncClient):
        """Test listing amenities when none exist."""
        with patch(
            "app.services.property.get_all_amenities",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = []

            response = await client.get("/api/v1/amenities/")

            assert response.status_code == 200
            data = response.json()
            assert data == []
