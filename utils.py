import asyncio
from typing import Any, Optional
from config import settings
import httpx

from pyrus_api_service import api_request


async def open_chat(
    task_id: int, json_data : dict[str, str| dict[str, str]] ={"text": "Чат открыт.", "channel": {"type": "telegram"}}
)-> dict[str, Any]:
    """Open chat in task in Pyrus"""
    return await api_request(
        method="POST",
        endpoint=f"/tasks/{task_id}/comments",
        json_data=json_data,
    )


def find_value(fields: list[dict[str, Any]], field_id: int) -> Optional[str | int]:
    """Finds a value in the fields by its ID"""
    for field in fields:
        if field.get("id") == field_id:
            return field.get("value")
    return None

async def download_one(
    client: httpx.AsyncClient, attachment: dict[str, Any], headers: dict[str, str]
) -> dict[str, Any]:
    """Downloads a single file from Pyrus attachment"""
    file_url = attachment.get("url")
    size = attachment.get("size")

    if not file_url or not size or size > settings.MAX_FILE_SIZE:
        return {"error": "No URL or size found in attachment"}

    attachment_id = attachment.get("id")

    url = (
        attachment.get("url")
        or f"https://api.pyrus.com/v4/files/download/{attachment_id}"
    )

    try:
        response = await api_request("GET", url)
        content = await response.read()
        return {"filename": attachment.get("name"), "content": response.content}
    except httpx.HTTPError as e:
        return {"error": str(e)}


async def download_files(
    attachments: list[dict[str, Any]], headers: dict[str, str], timeout: float = 30.0
) -> list[dict[str, Any]]:
    """Downloads files from Pyrus attachments"""

    limits = httpx.Limits(max_connections=25)

    async with httpx.AsyncClient(
        headers=headers, timeout=timeout, limits=limits
    ) as client:
        
        tasks = [download_one(client, att, headers) for att in attachments]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    return results
