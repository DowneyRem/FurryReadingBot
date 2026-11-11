"""Telegram 统一回复适配器。"""

from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import ContextTypes


async def reply(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		text: str, *, delete_after: float = 3, **kwargs) -> None:
	"""统一回复；delete_after 秒后自动删除提示消息。"""
	if update.effective_message:
		message = await update.effective_message.reply_text(text, **kwargs)
	elif update.effective_chat:
		message = await context.bot.send_message(
			chat_id=update.effective_chat.id, text=text, **kwargs)
	else:
		message = None

	if message and delete_after:
		await asyncio.sleep(delete_after)
		await message.delete()
