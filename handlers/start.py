from telegram import Update
from telegram.ext import ContextTypes

from config import FURRY_READING


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	text = [
		f"你好,我是 {FURRY_READING} 的小说分享投稿 Bot",
		f"向我发送 Linpx 小说链接即可分享小说",
		f"查看命令可用 /help"
	]
	await update.message.reply_text("\n".join(text))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	text = [
		"/start 开始",
		"/help 查看命令",
		# "/ping 查看 uid 和语言",
		"/down 下载并分享",
		"/black 申请下架（作者 ID 或主页链接）",
		"/review 仅管理员：重新推送待审核申请",
	]
	await update.message.reply_text("\n".join(text))


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	text = [
		f"chat_id: <code>{update.message.chat.id}</code>",
		f"language: <code>{update.message.from_user.language_code}</code>",
	]
	await update.message.reply_text(text="\n".join(text), parse_mode="HTML")
