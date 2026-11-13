"""Telegram 统一回复适配器。"""

from __future__ import annotations

import asyncio
import logging

from telegram import Message, Update
from telegram.ext import ContextTypes


logger = logging.getLogger(__name__)


async def reply(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		text: str, *, delete_after: float = 3, **kwargs) -> None:
	"""统一回复；delete_after 秒后在后台删除提示消息，不占用当前 handler。"""
	if update.effective_message:
		message = await update.effective_message.reply_text(text, **kwargs)
	elif update.effective_chat:
		message = await context.bot.send_message(
			chat_id=update.effective_chat.id, text=text, **kwargs)
	else:
		message = None

	if message and delete_after:
		delete_later(context, message, delete_after)


def delete_later(
		context: ContextTypes.DEFAULT_TYPE, message: Message, delay: float) -> None:
	"""在后台等待 delay 秒后删除消息；删除失败（已被删、权限变化）只记日志。"""

	async def run() -> None:
		await asyncio.sleep(delay)
		try:
			await message.delete()
		except Exception:
			logger.debug("延时删除消息失败", exc_info=True)

	context.application.create_task(run())
