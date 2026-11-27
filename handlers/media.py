"""私聊图片：作为「作者申请下架」的材料提交。

图片消息（`message.photo`）和「以文件发送的图片」（`message.document` 且
MIME 为 `image/*`）都接受：以文件发送不会被 Telegram 压缩，截图的字更清楚。

只有在该用户存在「等截图」的申请时才会处理；其他图片一律静默忽略，
避免把普通私聊图片当材料、也避免打扰用户。

例外：如果他的受理已过期、且被别人的新受理接手（`reopened`），
会回一句「请重新发送作者主页链接，再点🈲申请下架」——不能让截图静默消失。
"""

from __future__ import annotations

import logging

from telegram import Message, Update
from telegram.ext import ContextTypes

from handlers.telegram import send_blacklist_card
from services import BlacklistService


logger = logging.getLogger(__name__)


def material_file_id(message: Message) -> str | None:
	"""取消息里的图片 file_id：优先图片消息，其次 MIME 是 `image/*` 的文件。"""
	photos = message.photo
	if photos:
		return photos[-1].file_id
	document = message.document
	if document is None:
		return None
	mime = document.mime_type or ""
	if not mime.startswith("image/"):
		return None
	return document.file_id


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/photo 或图片文件：把截图挂到申请上，并送中转频道核验。"""
	message = update.effective_message
	user = update.effective_user
	if message is None or user is None:
		return

	file_id = material_file_id(message)
	if not file_id:
		return

	result = BlacklistService().submit_material(user.id, file_id)

	if result.status == "no_request":
		return
	if result.status == "expired":
		await message.reply_text(
			"截图提交超时，请重新发送作者主页链接，再点「🈲 申请下架」。")
		return
	if result.status == "reopened":
		await message.reply_text(
			"你之前的申请等待截图超时，已被新的申请接替；"
			"如需下架，请重新发送作者主页链接，再点「🈲 申请下架」。")
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
