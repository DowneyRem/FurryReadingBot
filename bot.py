"""
python-telegram-bot v21 最小空壳
运行前：设置环境变量 BOT_TOKEN，或同目录放 .env
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
	Application,
	CommandHandler,
	ContextTypes,
	MessageHandler,
	filters,
)

from utils.links import get_id, get_url


load_dotenv()  # 读取 .env 里的 BOT_TOKEN

logging.basicConfig(
	format="%(asctime)s %(levelname)s %(name)s: %(message)s",
	level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- handlers（业务都写在这种异步函数里）----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""处理 /start"""
	user = update.effective_user
	name = user.first_name if user else "朋友"
	if update.message:
		await update.message.reply_text(f"你好，{name}！这是一个空壳 Bot。")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""处理 /help"""
	if update.message:
		await update.message.reply_text("可用命令：/start /help")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""收到普通文字就原样回复（学习用）"""
	link = get_url(update.message.text)
	if isinstance(link, str):
		await update.message.reply_text(link)
	elif isinstance(link, list):
		await update.message.reply_text("\n".join(link))


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text(
		f"chat_id: <code>{update.message.chat.id}</code>\n"
		f"language: <code>{update.message.from_user.language_code}</code>",
		parse_mode="HTML")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""全局错误日志"""
	logger.exception("更新处理出错: %s", context.error)


# ---------- 组装 Application ----------
def main() -> None:
	token = os.environ.get("BOT_TOKEN", "").strip()
	if not token:
		raise SystemExit("请设置环境变量 BOT_TOKEN，或在 .env 中写入 BOT_TOKEN=...")
	
	# 构建应用（v20+ 的核心对象）
	app = (
		Application.builder()
		.token(token)
		.build()
	)
	
	# 注册命令
	app.add_handler(CommandHandler("start", start))
	app.add_handler(CommandHandler("help", help_cmd))
	app.add_handler(CommandHandler("ping", ping))
	
	# 注册「非命令的私聊文字」
	app.add_handler(
		MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, echo)
	)
	
	# 错误处理
	app.add_error_handler(error_handler)
	
	logger.info("Bot 启动中……")
	print("Bot 启动中……")
	app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
	main()