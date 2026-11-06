"""
python-telegram-bot v21 最小空壳
运行前：设置环境变量 BOT_TOKEN，或同目录放 .env
"""

from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import (
	Application,
	CommandHandler,
	ContextTypes,
	MessageHandler,
	CallbackQueryHandler,
	filters,
)

from core import down
from config import *

logging.basicConfig(
	format="%(asctime)s %(levelname)s %(name)s: %(message)s",
	level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
	query = update.callback_query
	await query.answer()
	if query.data != "":
		await query.edit_message_reply_markup(reply_markup=None)
	
	if query.data == "ignore":
		await query.delete_message()
	
	elif query.data.startswith("apply_furry_author:"):
		author_id = query.data.split(":", 1)[1]
		await query.message.reply_text(f"作者ID {author_id}")


# ---------- 组装 Application ----------
def main() -> None:
	if not BOT_TOKEN:
		raise SystemExit("请设置环境变量 BOT_TOKEN，或在 .env 中写入 BOT_TOKEN=...")
	
	# 构建应用（v20+ 的核心对象）
	app = (Application.builder().token(BOT_TOKEN).build())
	
	# 注册命令
	app.add_handler(CommandHandler("start", start))
	app.add_handler(CommandHandler("help", help_cmd))
	app.add_handler(CommandHandler("ping", ping))
	app.add_handler(CommandHandler("down", down))
	
	# 注册「非命令的私聊文字」
	app.add_handler(
		MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, down)
	)
	app.add_handler(CallbackQueryHandler(button_callback))
	
	# 错误处理
	app.add_error_handler(error_handler)
	
	logger.info("Bot 启动中……")
	print("Bot 启动中……")
	app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
	main()