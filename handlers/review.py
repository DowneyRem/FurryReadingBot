"""管理员命令：把待审核的申请重新送进中转频道。"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks.common import get_applications, send_to_transit
from storage.application import ApplicationStore


logger = logging.getLogger(__name__)


async def review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/review：重新推送全部待审核申请到中转频道，便于管理员核验。"""
	message = update.effective_message
	user = update.effective_user
	if message is None or user is None:
		return

	records = [
		record for record in get_applications().records().values()
		if record.status == ApplicationStore.STATUS_PENDING
	]
	if not records:
		await message.reply_text("✅ 当前没有待审核的申请")
		return

	sent = 0
	for record in records:
		if await send_to_transit(update, context, record):
			sent += 1

	logger.info("管理员 %s 重新推送待审核申请 %s/%s", user.id, sent, len(records))
	await message.reply_text(
		f"✅ 已重新发送 {sent}/{len(records)} 条待审核申请到中转频道，请前往核验")
