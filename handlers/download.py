from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes

from utils.links import get_id, get_url
from storage.list import ListManager
from keyboards import apply_furry_keyboard, down_novel_keyboard, down_novel_series_keyboard, down_series_keyboard, down_author_keyboard
from sources import fetch_novel
from config import FURRY_READING, FURRY_NOVELS


async def check_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if not update.message or not update.message.text:
		return
	
	link = get_url(update.message.text)
	try:
		novel = await fetch_novel(link)
	except ValueError as e:
		await update.message.reply_text(str(e))
		return
	except Exception:
		await update.message.reply_text("拉取小说失败，请稍后重试")
		return
	
	author_id = novel.author_id
	author_name = novel.author_name
	mgr = ListManager()
	
	if mgr.is_blacklisted(author_id):
		if not author_name:
			author_name = mgr.blacklist.get_name(author_id)
		await update.message.reply_text(f"不好意思，作者 {author_name} 已禁止通过本 Bot 下载小说并分享至 {FURRY_READING} 以及 {FURRY_NOVELS}")
	
	elif not mgr.is_blacklisted(author_id) and not mgr.is_furryauthor(author_id):
		await update.message.reply_text(
			text=f"不好意思，本 Bot 仅可下载小说并分享兽人小说。{author_name} 不在本 Bot 的兽人作者名单内",
			reply_markup=apply_furry_keyboard(link, author_id)
		)
		
	elif mgr.is_furryauthor(author_id):
		if "novel" in link or "pn" in link:
			if novel.series_id:
				await update.message.reply_text(
					text=f"{author_name}",
					reply_markup=down_novel_series_keyboard(link)
				)
			else:
				await update.message.reply_text(
					text=f"{author_name}",
					reply_markup=down_novel_keyboard(link)
				)
				
		elif "series" in link:
			await update.message.reply_text(
				text=f"{author_name}",
				reply_markup=down_series_keyboard(link)
			)
			
		elif "user" in link:
			await update.message.reply_text(
				text=f"{author_name}",
				reply_markup=down_author_keyboard(link)
			)
			
			