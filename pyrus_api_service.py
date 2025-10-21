import asyncio
import logging
from typing import Any, Optional
import httpx
from config import settings
from tenacity import retry, stop_after_attempt, wait_exponential


logger = logging.getLogger(__name__)

class TokenManager:
    def __init__(self):
        self._token: str | None = None
        self._lock = asyncio.Lock()

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_token(self) -> str:
        """Returns the current token, refreshing it if necessary."""
        if self._token:
            return self._token

        async with self._lock:
            if self._token:
                return self._token
            await self._refresh_token()

            if not self._token:
                raise RuntimeError("Failed to obtain token — _refresh_token did not set value")

            return self._token

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _refresh_token(self):
        logger.info("🔄 Refreshing token.")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.BASE_URL}/auth",
                json={
                    "login": settings.LOGIN,
                    "security_key": settings.SECURITY_KEY,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
        logger.info("✅ Token refreshed.")

    async def invalidate(self):
        """Resets the token if the error is 404"""
        self._token = None

token_manager = TokenManager()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def api_request(
    method: str,
    endpoint: str,
    json_data: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Makes an API request to Pyrus"""
    url = f"{settings.BASE_URL}{endpoint}"
    token = await token_manager.get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            json=json_data,
            params=params,
            timeout=30.0,
        )

        if response.status_code == 401:
            await token_manager.invalidate()

    response.raise_for_status()
    return response.json()
