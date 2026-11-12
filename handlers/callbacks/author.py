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


async def back_author(update: Update, context: ContextTypes.DEFAULT_TYPE,
	*, data: str) -> None:
	link = _link_from_data(data)
	item = await fetch(link)
	text = [
		"不好意思，本 Bot 仅可下载、分享兽人小说。",
		f"作者：{item.author_name}（#a{item.author_id}）目前不在兽人作者名单", "",
		f"申请其为兽人小说作者？",
		f"如需下载其他 Pixiv 小说，可以使用 @PixivNBot",
	]
	await update.callback_query.edit_message_text(
		text="\n".join(text),
		reply_markup=apply_author_keyboard(item.author_url),
	)
