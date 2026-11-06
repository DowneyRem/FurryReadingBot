from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from utils.links import get_id, get_url
from storage.list import ListManager
from keyboards import apply_furry_keyboard
from config import FURRY_READING, FURRY_NOVELS


async def down(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	link = get_url(update.message.text)[0]
	author_id = get_id(update.message.text)
	mgr = ListManager()
	if mgr.is_blacklisted(author_id):
		author_name = mgr.blacklist.get_name(author_id)
		await update.message.reply_text(f"不好意思，作者 {author_name} 已禁止通过本 Bot 下载小说并分享至 {FURRY_READING} 以及 {FURRY_NOVELS}")
	
	elif not mgr.is_blacklisted(author_id) and not mgr.is_furryauthor(author_id):
		author_name = "12345"
		await update.message.reply_text(
			text=f"不好意思，本 Bot 仅可下载小说并分享兽人小说。{author_name} 不在本 Bot 的兽人作者名单内",
			reply_markup=apply_furry_keyboard(link))
		
	elif mgr.is_furryauthor(author_id):
		author_name = mgr.furrylist.get_name(author_id)
		await update.message.reply_text(f"{author_name}")
		
		