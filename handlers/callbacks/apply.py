"""申请 / 审核类 callback：af / ifa。"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks._common import reply


async def handle_apply_furry(
	update: Update,
	context: ContextTypes.DEFAULT_TYPE,
	*,
	action: str,
	rest: str,
	data: str,
) -> None:
	# rest: "{link};{author_id}"
	parts = rest.split(";")
	link = parts[0] if parts else ""
	author_id = parts[1] if len(parts) > 1 else ""
	await reply(
		update,
		context,
		f"申请已记录（author={author_id}），管理员将审核。",
	)


async def handle_confirm_furry(
	update: Update,
	context: ContextTypes.DEFAULT_TYPE,
	*,
	action: str,
	rest: str,
	data: str,
) -> None:
	await reply(update, context, "管理员确认逻辑待接 ListManager.add_furrylist")
