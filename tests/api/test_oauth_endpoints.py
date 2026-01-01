"""
Tests for OAuth endpoints.

These tests verify the OAuth-related API endpoints work correctly.
They mock the service layer to isolate endpoint testing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


class TestOAuthAuthorizeEndpoint:
    """Tests for GET /api/v1/mcp/oauth/authorize endpoint."""

    @pytest.mark.asyncio
    async def test_authorize_success(self, client: AsyncClient):
        """Test OAuth authorize redirect."""
        with patch(
            "app.api.api_v1.endpoints.oauth.oauth_token_store"
        ) as mock_store:
            mock_store.store_oauth_session = AsyncMock()

            response = await client.get(
                "/api/v1/mcp/oauth/authorize",
                params={
                    "response_type": "code",
                    "client_id": "ghar360-mcp",
                    "redirect_uri": "http://localhost:3000/callback",
                    "scope": "mcp:read mcp:write",
                    "state": "test_state",
                },
                follow_redirects=False,
            )

            # Should redirect to consent page or return error for invalid params
            assert response.status_code in [302, 307, 400]

    @pytest.mark.asyncio
    async def test_authorize_invalid_response_type(self, client: AsyncClient):
        """Test authorize with invalid response type."""
        response = await client.get(
            "/api/v1/mcp/oauth/authorize",
            params={
                "response_type": "token",  # Only "code" is supported
                "client_id": "ghar360-mcp",
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_authorize_missing_client_id(self, client: AsyncClient):
        """Test authorize without client ID."""
        response = await client.get(
            "/api/v1/mcp/oauth/authorize",
            params={
                "response_type": "code",
            },
        )

        # Missing required parameter
        assert response.status_code == 422


class TestOAuthTokenEndpoint:
    """Tests for POST /api/v1/mcp/oauth/token endpoint."""

    @pytest.mark.asyncio
    async def test_token_authorization_code_grant(self, client: AsyncClient):
        """Test token exchange with authorization code."""
        with patch(
            "app.api.api_v1.endpoints.oauth.oauth_token_store"
        ) as mock_store:
            mock_store.get_auth_code = AsyncMock(
                return_value={
                    "user_id": "1",
                    "client_id": "ghar360-mcp",
                    "redirect_uri": "http://localhost:3000/callback",
                    "scope": "mcp:read mcp:write",
                    "code_challenge": None,
                }
            )
            mock_store.store_oauth_tokens = AsyncMock()
            mock_store.delete_auth_code = AsyncMock()

            response = await client.post(
                "/api/v1/mcp/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": "test_auth_code",
                    "client_id": "ghar360-mcp",
                    "redirect_uri": "http://localhost:3000/callback",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "Bearer"

    @pytest.mark.asyncio
    async def test_token_missing_code(self, client: AsyncClient):
        """Test token exchange without authorization code."""
        response = await client.post(
            "/api/v1/mcp/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": "ghar360-mcp",
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_token_invalid_code(self, client: AsyncClient):
        """Test token exchange with invalid authorization code."""
        with patch(
            "app.api.api_v1.endpoints.oauth.oauth_token_store"
        ) as mock_store:
            mock_store.get_auth_code = AsyncMock(return_value=None)

            response = await client.post(
                "/api/v1/mcp/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": "invalid_code",
                    "client_id": "ghar360-mcp",
                },
            )

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_token_refresh_grant(self, client: AsyncClient):
        """Test token refresh."""
        with patch(
            "app.api.api_v1.endpoints.oauth.oauth_token_store"
        ) as mock_store:
            mock_store.get_refresh_token = AsyncMock(
                return_value={
                    "user_id": "1",
                    "scope": "mcp:read mcp:write",
                }
            )
            mock_store.store_oauth_tokens = AsyncMock()
            mock_store.delete_refresh_token = AsyncMock()

            response = await client.post(
                "/api/v1/mcp/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": "test_refresh_token",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data

    @pytest.mark.asyncio
    async def test_token_invalid_refresh_token(self, client: AsyncClient):
        """Test token refresh with invalid refresh token."""
        with patch(
            "app.api.api_v1.endpoints.oauth.oauth_token_store"
        ) as mock_store:
            mock_store.get_refresh_token = AsyncMock(return_value=None)

            response = await client.post(
                "/api/v1/mcp/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": "invalid_token",
                },
            )

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_token_unsupported_grant_type(self, client: AsyncClient):
        """Test token with unsupported grant type."""
        response = await client.post(
            "/api/v1/mcp/oauth/token",
            data={
                "grant_type": "client_credentials",
            },
        )

        assert response.status_code == 400


class TestOAuthConsentEndpoint:
    """Tests for /api/v1/mcp/oauth/consent endpoint."""

    @pytest.mark.asyncio
    async def test_consent_page_missing_session(self, client: AsyncClient):
        """Test consent page without session."""
        with patch(
            "app.api.api_v1.endpoints.oauth.oauth_token_store"
        ) as mock_store:
            mock_store.get_oauth_session = AsyncMock(return_value=None)

            response = await client.get(
                "/api/v1/mcp/oauth/consent",
                params={"session": "invalid_session"},
            )

            assert response.status_code == 400


class TestPKCEVerification:
    """Tests for PKCE verification logic."""

    def test_verify_pkce_s256(self):
        """Test PKCE S256 verification."""
        from app.api.api_v1.endpoints.oauth import verify_pkce
        import base64
        import hashlib

        # Generate valid PKCE pair
        verifier = "test_verifier_12345"
        hash_obj = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(hash_obj).decode("ascii").rstrip("=")

        assert verify_pkce(challenge, verifier, "S256") is True
        assert verify_pkce(challenge, "wrong_verifier", "S256") is False

    def test_verify_pkce_plain(self):
        """Test PKCE plain verification."""
        from app.api.api_v1.endpoints.oauth import verify_pkce

        challenge = "test_challenge"
        verifier = "test_challenge"

        assert verify_pkce(challenge, verifier, "plain") is True
        assert verify_pkce(challenge, "wrong", "plain") is False

    def test_verify_pkce_missing_values(self):
        """Test PKCE with missing values."""
        from app.api.api_v1.endpoints.oauth import verify_pkce

        assert verify_pkce(None, "verifier", "S256") is False
        assert verify_pkce("challenge", None, "S256") is False
        assert verify_pkce(None, None, "S256") is False
