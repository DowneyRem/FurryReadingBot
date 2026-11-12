from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from sources import fetch
from keyboards import apply_author_keyboard, down_author_keyboard


def _link_from_data(data: str) -> str:
	parts = data.split(";", 1)
	return parts[1].strip() if len(parts) > 1 else ""


async def see_author(update: Update, context: ContextTypes.DEFAULT_TYPE,
	*, data: str) -> None:

	link = _link_from_data(data)
	item = await fetch(link)
	author_url = item.author_url
	author = await fetch(author_url)
	await update.callback_query.edit_message_text(
		text=str(author),
		reply_markup=down_author_keyboard(author_url)
	)

