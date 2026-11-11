"""私聊图片：作为「作者申请下架」的材料提交。

只有在该用户存在「等截图」的申请时才会处理；其他图片一律静默忽略，
避免把普通私聊图片当材料、也避免打扰用户。
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.telegram import send_blacklist_card
from services import BlacklistService


logger = logging.getLogger(__name__)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/photo：把截图挂到申请上，并送中转频道核验。"""
	message = update.effective_message
	user = update.effective_user
	if message is None or user is None or not message.photo:
		return

	result = BlacklistService().submit_material(
		user.id, message.photo[-1].file_id)

	if result.status == "no_request":
		return
	if result.status == "expired":
		await message.reply_text(
			"截图提交超时，请重新发送作者主页链接，再点「🈲 申请黑名单」。")
		return

	record = result.record
	if record is None or not await send_blacklist_card(context, record):
		await message.reply_text(
			"材料已收到，但送审失败（可能未配置中转频道），请联系管理员。")
		return

	logger.info(
		"作者下架材料已送审 author=%s user=%s",
		record.author_id, user.id)
	await message.reply_text("✅ 材料已收到，管理员核验后会私聊通知你结果。")
