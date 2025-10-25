import asyncio
import logging
from typing import Any, Optional
import httpx
from config import settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception


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
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
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


token_manager: TokenManager | None = None


def get_token_manager() -> TokenManager:
    """Returns a singleton TokenManager instance."""
    global token_manager
    if token_manager is None:
        token_manager = TokenManager()
    return token_manager


def retry_on_exception(exc: BaseException) -> bool:
    """Returns True if the exception should trigger a retry."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 403:
        return False
    return True


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10), retry=retry_if_exception(retry_on_exception))
async def api_request(
    method: str,
    endpoint: str = "",
    url: Optional[str] = None,
    json_data: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    files: Optional[dict[str, tuple[Any]]] = None
) -> dict[str, Any] | bytes | None:
    """Makes an API request to Pyrus"""

    request_url = url if url else f"{settings.BASE_URL}{endpoint}"

    token = await get_token_manager().get_token()
    headers = {
        "Authorization": f"Bearer {token}",
    }
    try:

        async with httpx.AsyncClient() as client:

            if not files:
                response = await client.request(
                    method=method,
                    url=request_url,
                    headers=headers,
                    json=json_data,
                    params=params,
                    timeout=30.0,
                )
            else:
                response = await client.request(
                    method=method,
                    url=request_url,
                    headers=headers,
                    params=params,
                    timeout=30.0,
                    files=files  # type: ignore
                )

            if response.status_code == 401:
                await get_token_manager().invalidate()
                raise httpx.HTTPStatusError(
                    "Unauthorized", request=response.request, response=response
                )

            response.raise_for_status()

            if params and params.get("download"):
                return response.content

            return response.json()

    except httpx.HTTPStatusError as e:
        logger.info(f"HTTP error: {e.response.status_code} - {e.response.text}")
        raise

    except Exception as e:
        logger.error(f"Error during API request: {e}")
        raise
