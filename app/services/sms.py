from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_sms_client: httpx.AsyncClient | None = None


def _get_sms_client() -> httpx.AsyncClient:
    """Return a reusable SMS HTTP client."""
    global _sms_client
    if _sms_client is None or _sms_client.is_closed:
        _sms_client = httpx.AsyncClient(timeout=10)
    return _sms_client


async def close_sms_client() -> None:
    """Close the reusable SMS HTTP client."""
    global _sms_client
    if _sms_client is not None and not _sms_client.is_closed:
        await _sms_client.aclose()
    _sms_client = None


async def send_sms(
    *,
    phone_number: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Send an SMS via a generic HTTP API provider.

    The concrete provider is configured via settings.SMS_PROVIDER_API_URL
    and settings.SMS_PROVIDER_API_KEY. When not configured, this function
    is a no-op and returns False.
    """
    api_url = settings.SMS_PROVIDER_API_URL
    api_key = settings.SMS_PROVIDER_API_KEY
    sender_id = settings.SMS_SENDER_ID

    if not api_url or not api_key:
        logger.info(
            "SMS not sent: provider not configured",
            extra={"phone": phone_number},
        )
        return False

    payload: dict[str, Any] = {
        "to": phone_number,
        "message": message,
    }
    if sender_id:
        payload["sender_id"] = sender_id
    if metadata:
        payload["metadata"] = metadata

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        client = _get_sms_client()
        resp = await client.post(api_url, json=payload, headers=headers)
        if resp.status_code // 100 == 2:
            return True
        logger.error(
            "SMS send failed",
            extra={
                "phone": phone_number,
                "status": resp.status_code,
                "body": resp.text,
            },
        )
        return False
    except Exception as e:  # pragma: no cover - provider/network dependent
        logger.error(
            "SMS send exception",
            extra={"phone": phone_number, "error": str(e)},
        )
        return False
