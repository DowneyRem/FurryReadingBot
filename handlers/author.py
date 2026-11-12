"""/black：作者本人申请下架。参数是作者 ID 或作者主页链接。

带参数时给出确认键盘（`aby`），后续「材料 → 送审 → 核验」全复用
`handlers.callbacks.blacklist` 与 `services.blacklist_service`。
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks.blacklist import BLACKLIST_NOTICE
from keyboards import confirm_black_keyboard
from sources.linpx import LinpxSource
from sources.linpx.urls import url_author
from utils.links import get_id


BLACK_USAGE = "\n".join([
	"发送 Linpx 主页链接即可申请下架",
	"如：https://linpx.ink/pixiv/user/12345",
	"也可以发送作者 ID 或使用命令：/black 12345",
])


def _author_link(arg: str) -> str:
	"""把 /black 的参数（作者 ID 或主页链接）归一化成 Linpx 作者主页链接。"""
	value = (arg or "").strip()
	if not value:
		return ""
	if value.isdigit():
		return url_author(value)
	# 只接受作者主页链接；/cache、www. 之类写法统一成标准链接
	if not LinpxSource().is_author_link(value):
		return ""
	author_id = get_id(value)
	return url_author(author_id) if author_id else ""


async def black(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/black：带作者 ID / 主页链接时给出下架确认键盘，否则回用法提示。"""
	message = update.effective_message
	if message is None:
		return

	args = context.args or []
	link = _author_link(args[0]) if args else ""
	if not link:
		await message.reply_text(BLACK_USAGE, disable_web_page_preview=True)
		return

	await message.reply_text(
		BLACKLIST_NOTICE,
		reply_markup=confirm_black_keyboard(link),
		disable_web_page_preview=True,
	)
