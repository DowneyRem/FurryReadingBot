import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from utils.links import get_id, get_url
from list import ListManager


load_dotenv()  # 读取 .env
FURRY_READING = os.environ.get("FURRY_READING")
FURRY_NOVELS = os.environ.get("FURRY_NOVELS")


async def down(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	link = get_url(update.message.text)
	author_id = get_id(update.message.text)
	mgr = ListManager()
	if mgr.is_blacklisted(author_id):
		author_name = mgr.blacklist.get_name(author_id)
		await update.message.reply_text(f"不好意思，作者 {author_name} 已禁止通过本 Bot 下载小说并分享至 {FURRY_READING} 以及 {FURRY_NOVELS}")
	
	elif not mgr.is_blacklisted(author_id) and not mgr.is_furryauthor(author_id):
		author_name = "12345"
		await update.message.reply_text(
			text=f"不好意思，本 Bot 仅可下载小说并分享兽人小说。{author_name} 不在本 Bot 的兽人作者名单内",
			reply_markup=InlineKeyboardMarkup(
				[[
					InlineKeyboardButton(
						text="申请加入兽人作者名单",
						callback_data=f"apply_furry_author:{author_id}"),
					InlineKeyboardButton(
						text="忽略",
						callback_data="ignore"),
				]])
		)
		
	elif mgr.is_furryauthor(author_id):
		author_name = mgr.furrylist.get_name(author_id)
		await update.message.reply_text(f"{author_name}")
		
		