from pathlib import Path
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackContext

from utils.links import get_id, get_url
from storage.list import ListManager
from keyboards import apply_furry_keyboard
from sources import fetch_novel, save_novel
from config import FURRY_READING, FURRY_NOVELS


async def down(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
			reply_markup=apply_furry_keyboard(link))
		
	elif mgr.is_furryauthor(author_id):
		if not author_name:
			author_name = mgr.furrylist.get_name(author_id)
		await update.message.reply_text(f"{author_name}")
		
		try:
			path = await save_novel(link)
			with open(path, "rb") as file_object:
				message = await update.message.reply_document(
					document=file_object,
					filename=Path(path).name,
					caption="这是为您准备的文件！",
					# reply_to_message_id=update.message.message_id
				)
				
			file_id = message.document.file_id
			await message.reply_text(file_id)
			# todo：存储file id 避免重复上传
		
		except FileNotFoundError:
			# 容错处理：如果文件不存在，通知用户
			await update.message.reply_text("抱歉，未找到指定的文件。")
		except Exception as e:
			# 捕获其他潜在异常（如网络问题或权限问题）
			await update.message.reply_text(f"文件发送失败，错误信息: {e}")
		