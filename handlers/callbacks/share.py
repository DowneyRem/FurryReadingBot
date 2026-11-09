"""分享类 callback：snp / sna / snn。"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks._common import reply


async def handle_share_public(
	update: Update,
	context: ContextTypes.DEFAULT_TYPE,
	*,
	action: str,
	rest: str,
	data: str,
) -> None:
	await reply(update, context, "公开分享逻辑待接频道配置")


async def handle_share_private(
	update: Update,
	context: ContextTypes.DEFAULT_TYPE,
	*,
	action: str,
	rest: str,
	data: str,
) -> None:
	await reply(update, context, "私密分享逻辑待接")


async def handle_share_reject(
	update: Update,
	context: ContextTypes.DEFAULT_TYPE,
	*,
	action: str,
	rest: str,
	data: str,
) -> None:
	await reply(update, context, "已拒绝分享")
