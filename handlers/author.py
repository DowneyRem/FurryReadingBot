"""作者相关命令：`/black` 申请下架、`/furry` 申请加入兽人作者名单。

两个命令共用同一套参数解析（作者 ID 或作者主页链接）；后续流程分别复用
`handlers.callbacks.blacklist`（材料 → 送审 → 核验）与
`handlers.callbacks.apply`（后果告知 → 确认 → 送审）。
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks.apply import apply_furry
from handlers.callbacks.blacklist import BLACKLIST_NOTICE
from keyboards import confirm_black_keyboard
from sources import resolve_source
from sources.errors import SourceError
from sources.pixiv.urls import url_author
from utils.links import get_id


logger = logging.getLogger(__name__)


BLACK_USAGE = "\n".join([
	"发送 Pixiv 或 Linpx 作者主页链接即可申请下架",
	"如：https://www.pixiv.net/users/12345",
	"也可以发送作者 ID 或使用命令：/black 12345",
])

FURRY_USAGE = "\n".join([
	"发送 Pixiv 或 Linpx 作者主页链接即可申请加入兽人作者名单",
	"如：https://www.pixiv.net/users/12345",
	"也可以发送作者 ID 或使用命令：/furry 12345",
])


def _author_link(arg: str) -> str:
	"""把 /black、/furry 的参数（作者 ID 或主页链接）归一化成 Pixiv 作者主页链接。"""
	value = (arg or "").strip()
	if not value:
		return ""
	if value.isdigit():
		return url_author(value)
	source = resolve_source(value)
	if source is None or not source.is_author_link(value):
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


async def furry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/furry：带作者 ID / 主页链接时给出兽人作者申请确认键盘。"""
	message = update.effective_message
	if message is None:
		return

	args = context.args or []
	link = _author_link(args[0]) if args else ""
	if not link:
		await message.reply_text(FURRY_USAGE, disable_web_page_preview=True)
		return

	try:
		# 复用按钮入口：已拉黑 / 已在名单 / 审核中的状态检查都在这里
		await apply_furry(update, context, data=f"af;{link}")
	except SourceError as e:
		await message.reply_text(str(e))
	except Exception:
		logger.exception("兽人作者申请检查失败 link=%s", link)
		await message.reply_text(
			"获取作者信息失败，请稍后再试，或直接发送作者主页链接。")
