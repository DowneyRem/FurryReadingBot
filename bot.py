from __future__ import annotations

import logging
from telegram.ext import (
	Application,
	CommandHandler,
	MessageHandler,
	CallbackQueryHandler,
	filters,
)

from handlers import *
from config import *
from infra.http import close_http

logging.basicConfig(
	format="%(asctime)s %(levelname)s %(name)s: %(message)s",
	level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context) -> None:
	logger.exception("更新处理出错: %s", context.error)


async def post_shutdown(application: Application) -> None:
	"""退出时关闭复用的 aiohttp 会话。"""
	await close_http()


def main() -> None:
	if not BOT_TOKEN:
		raise SystemExit("请设置环境变量 BOT_TOKEN，或在 .env 中写入 BOT_TOKEN=...")

	# 构建应用（v20+ 的核心对象）
	# concurrent_updates：update 并行处理；用 config 里的有界值，不用 True（True = 256 路）
	# post_shutdown：退出时关掉复用的 aiohttp 会话（v20+ 只能通过 builder 传，不是 setter）
	app = (
		Application.builder()
		.token(BOT_TOKEN)
		.concurrent_updates(CONCURRENT_UPDATES)
		.post_shutdown(post_shutdown)
		.build()
	)

	# 注册命令
	app.add_handler(CommandHandler("start", start))
	app.add_handler(CommandHandler("help", help_cmd))
	app.add_handler(CommandHandler("ping", ping))
	app.add_handler(CommandHandler("down", download))
	app.add_handler(CommandHandler("review", review))
	app.add_handler(CommandHandler("black", black))
	app.add_handler(CommandHandler("furry", furry))

	# 注册「非命令的私聊文字」
	app.add_handler(
		MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, download)
	)
	# 私聊图片：作者下架申请的材料
	app.add_handler(
		MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, on_photo)
	)

	app.add_handler(CallbackQueryHandler(button_callback))
	app.add_error_handler(error_handler)

	logger.info("Bot 启动中……")
	print("Bot 启动中……")
	app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
	main()
