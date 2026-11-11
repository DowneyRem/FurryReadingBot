from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	user = update.effective_user
	name = user.first_name if user else "朋友"
	if update.message:
		await update.message.reply_text(f"你好，{name}！这是一个空壳 Bot。")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.message:
		await update.message.reply_text(
			"可用命令：/start /help /ping /down\n"
			"管理员：/review（把待审核的申请重新送进中转频道）")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text(
		f"chat_id: <code>{update.message.chat.id}</code>\n"
		f"language: <code>{update.message.from_user.language_code}</code>",
		parse_mode="HTML",
	)
