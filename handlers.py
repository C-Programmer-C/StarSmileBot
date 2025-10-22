from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from db import get_user

start_router = Router()

@start_router.message(F.text)
async def message_text_handler(message: Message):

    if not isinstance(message, Message):
        message.answer("Ошибка: неверный тип сообщения. Попробуйте еще раз.")
        return

    if not message.from_user:
        message.answer("Ошибка: не удалось получить информацию о пользователе. Попробуйте еще раз.")
        return

    tg_id = message.from_user.id

    if not tg_id:
        message.answer("Ошибка: не удалось получить идентификатор пользователя. Попробуйте еще раз.")
        return
        
    user = get_user(tg_id)

    print(f'Пользователь: {user}')

    if not user:
        await message.answer("Вы не зарегистрированы. Пожалуйста, зарегистрируйтесь, чтобы продолжить.")

    
    