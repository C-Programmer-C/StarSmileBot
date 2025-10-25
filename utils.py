import asyncio
from io import BytesIO
import logging
from typing import Any, Dict, List, Optional
import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile, InputMediaDocument

from config import settings
from pyrus_api_service import api_request

logger = logging.getLogger(__name__)


async def open_chat(
    task_id: int,
    json_data: dict[str, str | dict[str, str]] = {
        "text": "Чат открыт.",
        "channel": {"type": "telegram"},
    },
) -> dict[str, Any]:
    """Open chat in task in Pyrus"""
    try:
        result = await api_request(
            method="POST", endpoint=f"/tasks/{task_id}/comments", json_data=json_data
        )
        if not isinstance(result, dict):
            raise TypeError("Expected dict response")
        return result
    except Exception as e:
        logger.error(f"Failed to open chat for task {task_id}: {e}")
        raise


def prepare_fields_to_dict(fields: list[dict[str, Any]]) -> dict[int, str]:
    """Prepares a dictionary from Pyrus fields"""
    return {
        field["id"]: field["value"]
        for field in fields
        if "id" in field and "value" in field
    }


def find_value(fields: list[dict[str, Any]], field_id: int) -> Optional[str | int]:
    """Finds a value in the fields by its ID"""

    return next(
        (field.get("value") for field in fields if field.get("id") == field_id), None
    )


async def download_one(
    client: httpx.AsyncClient, attachment: dict[str, Any], headers: dict[str, str]
) -> dict[str, Any]:
    """Downloads a single file from Pyrus attachment"""
    file_url = attachment.get("url")
    size = attachment.get("size")
    name = attachment.get("name")
    attachment_id = attachment.get("id")
    if not name:
        logger.error("No filename in attachment")
        return {"error": "No filename"}

    if not file_url or not size:
        logger.error(f"No URL or size for file {name}")
        return {"error": "No URL or size"}

    if size > settings.MAX_FILE_SIZE:
        logger.warning(f"File {name} exceeds size limit")
        return {"error": "File too large"}

    try:
        download_url = f"https://api.pyrus.com/v4/files/download/{attachment_id}"

        logger.info(f"Downloading file from URL: {download_url}")

        response = await api_request(
            "GET",
            url=download_url,
            params={"download": True},
        )

        if not isinstance(response, bytes):
            logger.error(f"Invalid response type for {name}")
            return {"error": "Invalid response"}

        logger.info(
            f"Downloaded file {name} successfully. Content bytes: {response[:20]}..."
        )

        return {"filename": name, "content": response}

    except Exception as e:
        logger.exception(f"Failed to download {name}: {e}")
        return {"error": str(e)}


async def download_files(
    attachments: list[dict[str, Any]], headers: dict[str, str], timeout: float = 30.0
) -> list[dict[str, Any]]:
    """Downloads files from Pyrus attachments"""

    limits = httpx.Limits(max_connections=50)

    async with httpx.AsyncClient(
        headers=headers, timeout=timeout, limits=limits
    ) as client:

        tasks = [download_one(client, att, headers) for att in attachments]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    return results


def process_file_data(attach_data: dict[str, Any]) -> BufferedInputFile | None:
    """Processes file data from attachment"""
    content = attach_data.get("content")
    name = attach_data.get("filename")
    err = attach_data.get("error")
    if not content or not name or err:
        logger.warning("No content or name found in attachment data: %s", err)
        return None

    return BufferedInputFile(file=content, filename=name)


def chunk_list(seq: List[Any], chunk_size: int = 10) -> List[List[Any]]:
    """Chunks a list into smaller lists of a specified size."""
    return [seq[i : i + chunk_size] for i in range(0, len(seq), chunk_size)]


async def send_message_to_telegram_chat(
    bot: Bot,
    chat_id: int,
    text: Optional[str],
    attachments: list[dict[str, Any]] | None,
):
    """Sends a message and attachments to a Telegram chat."""
    try:
        if text:
            logger.info("Sending message to user #%d: %s", chat_id, text)
            await bot.send_message(chat_id=chat_id, text=text)

        if not attachments:
            logger.info("No attachments to send of user #%d", chat_id)
            return

        processed_files: list[InputMediaDocument] = []

        logger.info("Processing attachments for user #%d", chat_id)

        for file in attachments:
            if processed_file := process_file_data(file):
                processed_files.append(InputMediaDocument(media=processed_file))

        if not processed_files:
            logger.warning("No valid files found to send to user #%d", chat_id)
            return

        for chunk in chunk_list(processed_files):
            try:
                await bot.send_media_group(chat_id=chat_id, media=chunk)
                logger.info("Media chunk sent successfully to user #%d", chat_id)
            except Exception as e:
                logger.error(f"Failed to send media chunk: {e}")

    except Exception as e:
        logger.exception(f"Failed to send message to {chat_id}: {e}")
        raise


async def create_user_task(json_data: dict[str, Any]) -> dict[str, Any]:
    """Creates a new task in Pyrus for a user"""
    try:
        assert json_data, "json_data must not be empty"
        result = await api_request(
            method="POST", endpoint="/tasks", json_data=json_data
        )
        if not isinstance(result, dict):
            raise TypeError("Expected dict response")

        if task := result.get("task"):
            logger.info("✅ User task created with ID: %s", task.get("id"))
            return task
        return {}
    except Exception as e:
        logger.error(f"Failed to create user task: {e}")
        raise


async def check_api_element(tg_id: int, form_id: int, field_id: int) -> dict[str, Any] | None:
    """Checks if the API user is reachable"""
    result = await api_request(
        method="GET", endpoint=f"/forms/{form_id}/register?fld{field_id}={tg_id}"
    )
    if not isinstance(result, dict):
        raise TypeError("Expected dict response")

    tasks = result.get("tasks", [])
    if not tasks:
        logger.warning(f"No tasks found for TG ID {tg_id}")
        return

    task = tasks[0]

    return task



async def get_unique_file_id(
    file_bytes: BytesIO,
    filename: str,
) -> Optional[str]:
    """Uploads a file to Pyrus and returns its unique GUID"""

    try:
        files = {"file": (filename, file_bytes, "application/octet-stream")}

        result = await api_request(
            "POST", "/files/upload", files=files # type: ignore
        )

        if isinstance(result, dict):
            return result.get("guid")

    except Exception as e:
        logger.error(
            f"An error occurred while trying to get a unique ID file #{filename}: {e}"
        )
        return None


async def create_appeal_task(json_data: dict[str, Any]) -> dict[str, Any]:
    """Creates a new appeal task in Pyrus for a user"""
    try:
        assert json_data, "json_data must not be empty"
        result = await api_request(
            method="POST", endpoint="/tasks", json_data=json_data
        )
        if not isinstance(result, dict):
            raise TypeError("Expected dict response")

        if task := result.get("task"):
            logger.info("✅ Appeal task created with ID: %s", task.get("id"))
            return task
        return {}
    except Exception as e:
        logger.error(f"Failed to create appeal task: {e}")
        raise


def build_payload(
    text: Optional[str] = None, files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generates a payload for sending files via the API"""
    payload: Dict[str, Any] = {
        "channel": {
            "type": "telegram",
        },
    }

    if text:
        payload["text"] = text
    else:
        payload["text"] = "..."

    if files:
        payload["attachments"] = files

    return payload

async def send_comment_in_pyrus(task_id: int, json_data: Dict[str, Any]):
    """Sends a message to Pyrus"""
    result = await api_request("POST", f"/tasks/{task_id}/comments",json_data=json_data)
    task = result.get("task", {}) if isinstance(result, dict) else None
    if task:
        logger.info("The comment was sent successfully!")
