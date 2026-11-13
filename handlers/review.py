"""管理员命令：把待审核的申请重新送进中转频道。"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.telegram import send_blacklist_card, send_to_transit, transit_admin_policy
from services import ApplyService, BlacklistService


logger = logging.getLogger(__name__)


async def review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/review：重新推送全部待审核申请到中转频道，便于管理员核验。"""
	message = update.effective_message
	user = update.effective_user
	if message is None or user is None:
		return

	decision = await transit_admin_policy(context.bot).check(user.id)
	if not decision.allowed:
		await message.reply_text("⚠️ 仅中转频道管理员可以重新推送待审核申请")
		return

	furry = ApplyService().pending_records()
	takedown = BlacklistService().pending_review_records()
	total = len(furry) + len(takedown)
	if not total:
		await message.reply_text("✅ 当前没有待审核的申请")
		return

	sent = 0
	for record in furry:
		if await send_to_transit(update, context, record):
			sent += 1
	for record in takedown:
		if await send_blacklist_card(context, record):
			sent += 1

	logger.info("管理员 %s 重新推送待审核申请 %s/%s", user.id, sent, total)
	await message.reply_text(
		f"✅ 已重新发送 {sent}/{total} 条待审核申请到中转频道"
		f"（兽人作者 {len(furry)}，作者下架 {len(takedown)}），请前往核验")
