"""callbacks 包内共用小工具。"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
	if update.effective_message:
		await update.effective_message.reply_text(text)
	elif update.effective_chat is not None:
		await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
