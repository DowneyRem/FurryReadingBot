from telegram import Update
from telegram.ext import ContextTypes

from config import FURRY_NOVELS, FURRY_READING
from keyboards import (
	apply_furry_author_keyboard,
	down_author_keyboard,
	down_novel_keyboard,
	down_novel_series_keyboard,
	down_series_keyboard,
)
from sources import fetch
from sources.linpx.errors import LinpxError
from storage.list import ListManager
from utils.json import JsonDict
from utils.links import get_url


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	message = update.effective_message
	if message is None or not message.text:
		return

	link = get_url(message.text)
	if not isinstance(link, str) or not link:
		await message.reply_text("请发送一个有效的小说、系列或作者链接。")
		return
	
	try:
		if "novel" in link or "/pn/" in link:
			item = await fetch(link)
			if item.series_id:
				markup = down_novel_series_keyboard(link)
			else:
				markup = down_novel_keyboard(link)
			description = str(item)
			
		elif "series" in link:
			item = await fetch(link)
			markup = down_series_keyboard(link)
			description = str(item)
			
		elif "user" in link:
			item = await fetch(link)
			markup = down_author_keyboard(link)
			description = str(item)
			
		else:
			item = JsonDict({"author_id": "", "author_name": ""})
			markup = ""
			description = ""
			
	except LinpxError as e:
		await message.reply_text(f"发生 Linpx 错误\n{e}")
		return
	except Exception as e:
		await message.reply_text(f"发生未知错误\n{e}")
		return
	
	else:
		# print(description)
		author_id, author_name = item.author_id, item.author_name
		manager = ListManager()
		if manager.is_blacklisted(author_id):
			if not author_name:
				author_name = manager.blacklist.get_name(author_id)
			
			text = [
				f"不好意思，作者 {author_name} 已禁止通过本 Bot 下载小说并分享至 {FURRY_READING} 以及 {FURRY_NOVELS}",
				"如需下载其他 Pixiv 小说，可以使用 @PixivNBot",
			]
			await message.reply_text("\n".join(text))
			return
		
		if not manager.is_furryauthor(author_id):
			text = [
				f"不好意思，本 Bot 仅可下载兽人小说。",
				f"作者：{author_name}（#a{author_id}）目前不在兽人小说作者名单", "",
				"申请其为兽人小说作者？",
				"如需下载其他 Pixiv 小说，可以使用 @PixivNBot",
			]
			await message.reply_text(
				text="\n".join(text),
				reply_markup=apply_furry_author_keyboard(link, author_id),
			)
			return
	
		await message.reply_text(text=description, reply_markup=markup)