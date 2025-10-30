import asyncio
import logging
from typing import Any
from weakref import WeakValueDictionary
import httpx
from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.process_message import process_media_group, process_single_comment
from config import settings
from utils import (
    check_api_element,
    create_appeal_task,
    create_user_task,
    open_chat,
    prepare_fields_to_dict,
)

logger = logging.getLogger(__name__)

start_router = Router()

_user_locks = WeakValueDictionary()  # type: ignore

_locks_map_guard = asyncio.Lock()


async def get_user_lock(tg_id: int) -> asyncio.Lock:
    async with _locks_map_guard:
        lock = _user_locks.get(tg_id)  # type: ignore
        if lock is None:
            lock = asyncio.Lock()
            _user_locks[tg_id] = lock
        return lock  # type: ignore


class RegistrationState(StatesGroup):
    input_fullname = State()
    input_telephone = State()


@start_router.message(StateFilter(None))
async def message_text_handler(message: Message):

    if not message.from_user:
        message.answer(
            "Ошибка: не удалось получить информацию о пользователе. Попробуйте еще раз."
        )
        return

    tg_id = message.from_user.id

    if not tg_id:
        message.answer(
            "Ошибка: не удалось получить идентификатор пользователя. Попробуйте еще раз."
        )
        return

    lock = await get_user_lock(tg_id)

    async with lock:
        try:
            user = await check_api_element(
                tg_id, settings.CLIENT_FORM_ID, settings.USER_FORM_FIELDS["tg_id"]
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning(f"Access denied for user {tg_id}: {e}")
                user = None
            else:
                logger.error(f"HTTP error for user {tg_id}: {e}")
                message.answer(
                    "Ошибка при обработке запроса. Пожалуйста, попробуйте позже."
                )
                raise
        except Exception as e:
            logger.error(f"Unexpected error for user {tg_id}: {e}")
            message.answer(
                "Ошибка при обработке запроса. Пожалуйста, попробуйте позже."
            )
            raise

        user_id = user.get("id") if user else None

        if not user_id:
            await message.answer(
                "Вы не зарегистрированы. Пожалуйста, зарегистрируйтесь, чтобы продолжить.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Зарегистрироваться", callback_data="register"
                            )
                        ],
                    ],
                    resize_keyboard=True,
                ),
            )
            return

        assert user

        logger.info("User %s found in the system. User ID: %s", tg_id, user_id)

        fields = user.get("fields", [])

        if not fields:
            await message.answer(
                "Ошибка: не удалось получить данные пользователя. Попробуйте еще раз."
            )
            return

        task = await check_api_element(
            tg_id, settings.APPEAL_FORM_ID, settings.REQUEST_FORM_FIELDS["tg_id"]
        )

        task_id = task.get("id") if task else None

        logger.info(
            f"Processing message from user {tg_id}, existing appeal task ID: {task_id}"
        )

        if not task_id:

            logger.warning(
                f"No existing appeal task for user {tg_id}. Creating a new one."
            )

            fields_dict = prepare_fields_to_dict(fields)

            fullname = fields_dict.get(
                settings.USER_FORM_FIELDS["fullname"], "Пользователь"
            )
            telephone = fields_dict.get(
                settings.USER_FORM_FIELDS["telephone"], "Не указан"
            )
            tg_account = fields_dict.get(
                settings.USER_FORM_FIELDS["tg_account"], "Не указан"
            )

            json_data: dict[str, Any] = {
                "form_id": settings.APPEAL_FORM_ID,
                "fields": [
                    {"id": settings.REQUEST_FORM_FIELDS["tg_id"], "value": tg_id},
                    {"id": settings.REQUEST_FORM_FIELDS["fio"], "value": fullname},
                    {
                        "id": settings.REQUEST_FORM_FIELDS["telephone"],
                        "value": telephone,
                    },
                    {
                        "id": settings.REQUEST_FORM_FIELDS["tg_account"],
                        "value": tg_account,
                    },
                ],
            }

            result = await create_appeal_task(json_data)

            task_id = result.get("id")

            if result and task_id:

                logger.info(
                    f"Created new appeal task ID {result.get('id')} for user {tg_id}"
                )
            else:
                logger.error(f"Failed to create appeal task for user {tg_id}")
                await message.answer(
                    "Ошибка при создании обращения. Пожалуйста, попробуйте позже."
                )
                return

            success = await open_chat(task_id)

            if success:
                logger.info(
                    f"The chat for task #{task_id} has been successfully opened"
                )

    if not task_id:
        await message.answer(
            "Произошла ошибка при попытке получить данные в обращении."
        )
        return

    if message.media_group_id:
        logger.info(
            f"The media group #{message.media_group_id} processing for task #{task_id} process has begun"
        )
        await process_media_group(message, tg_id, task_id)
    else:
        logger.info(
            f"The message #{message.message_id} processing for task #{task_id} process has begun"
        )
        await process_single_comment(message, task_id)


@start_router.callback_query(F.data == "register", StateFilter(None))
async def register_callback_handler(
    callback_query: types.CallbackQuery, state: FSMContext
):
    if not callback_query.message:
        await callback_query.answer(
            "Ошибка: не удалось получить сообщение. Попробуйте еще раз."
        )
        return
    await callback_query.message.answer("Пожалуйста, введите ваше полное имя:")
    await state.set_state(RegistrationState.input_fullname)
    await callback_query.answer()


@start_router.message(RegistrationState.input_fullname)
async def input_fullname_handler(message: Message, state: FSMContext):
    if not message.text:
        await message.answer(
            "Ошибка: не удалось получить ваше имя. Пожалуйста, введите повторно ваше полное имя:"
        )
        return
    fullname = message.text.strip()
    await state.update_data(fullname=fullname)
    await message.answer("Пожалуйста, введите ваш номер телефона:")
    await state.set_state(RegistrationState.input_telephone)


@start_router.message(RegistrationState.input_telephone)
async def input_telephone_handler(message: Message, state: FSMContext):
    if not message.text:
        await message.answer(
            "Ошибка: не удалось получить ваш номер телефона. Пожалуйста, введите ваш номер телефона:"
        )
        return

    if not message.from_user:
        await message.answer(
            "Ошибка: не удалось получить информацию о пользователе. Попробуйте еще раз."
        )
        return
    data = await state.get_data()
    telephone = message.text.strip()
    fullname = data.get("fullname")
    tg_id = message.from_user.id
    tg_account = message.from_user.username

    json_data: dict[str, Any] = {
        "form_id": settings.CLIENT_FORM_ID,
        "fields": [
            {"id": settings.USER_FORM_FIELDS["fullname"], "value": fullname},
            {"id": settings.USER_FORM_FIELDS["telephone"], "value": telephone},
            {"id": settings.USER_FORM_FIELDS["tg_account"], "value": tg_account},
            {"id": settings.USER_FORM_FIELDS["tg_id"], "value": tg_id},
        ],
    }
    logger.info(
        f"User registration: {fullname}, Phone: {telephone}, TG ID: {tg_id}, TG Account: {tg_account}"
    )

    try:
        user_data = await create_user_task(json_data)
    except Exception as e:
        await message.answer(
            "Ошибка при попытке регистрации. Пожалуйста, попробуйте позже."
        )
        logger.error(f"Error creating user task for {tg_id}: {e}")
        await state.clear()
        return

    id = user_data.get("id")

    if not id:
        await message.answer(
            "Ошибка: не удалось зарегистрировать пользователя. Попробуйте еще раз."
        )
        await state.clear()
        return

    logger.info(
        f"User {fullname} successfully registered with TG ID {tg_id} and Task ID {id}"
    )

    await message.answer(f"Спасибо за регистрацию, {fullname}!")

    json_data = {
        "form_id": settings.APPEAL_FORM_ID,
        "fields": [
            {"id": settings.REQUEST_FORM_FIELDS["fio"], "value": fullname},
            {"id": settings.REQUEST_FORM_FIELDS["telephone"], "value": telephone},
            {"id": settings.REQUEST_FORM_FIELDS["tg_account"], "value": tg_account},
            {"id": settings.REQUEST_FORM_FIELDS["tg_id"], "value": tg_id},
        ],
    }

    result = await create_appeal_task(json_data)

    task_id = result.get("id")

    if result and task_id:

        logger.info(f"Created new appeal task ID {result.get('id')} for user {tg_id}")

    if not task_id:
        logger.error(f"Failed to create appeal task for user {tg_id}")
        await message.answer(
            "Ошибка при создании обращения. Пожалуйста, попробуйте позже."
        )
        return

    success = await open_chat(task_id)

    if success:
        logger.info(f"The chat for task #{task_id} has been successfully opened")

    await state.clear()
