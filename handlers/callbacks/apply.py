"""用户侧申请 callback：af（告知后果 + 二次确认）/ afy（提交申请）。

业务规则在 services.apply_service，管理核验在 handlers.callbacks.review，
公共 Telegram 工具在 handlers.telegram。
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.telegram import reply, send_to_transit
from keyboards import confirm_furry_keyboard
from services import ApplyInvalidLinkError, ApplyService


logger = logging.getLogger(__name__)


def apply_notice(author_name: str, author_id: str) -> str:
	"""申请前的后果告知"""
	message = [
		f"申请将作者 {author_name}（#a{author_id}）加入兽人作者名单前，请先确认你了解以下内容：", "",
		f"1. 申请通过后，方可下载、分享该作者的小说",
		f"2. 申请需要管理核验。申请期间，不能下载、分享该作者的小说",
		f"3. 作者事后可以投诉，届时将下架相关内容，并禁止下载、分享该作者的小说", "",
		"确认发起申请吗？"
	]
	return "\n".join(message)


def _link_from_data(data: str) -> str:
	parts = data.split(";", 1)
	if len(parts) < 2 or not parts[1]:
		raise ApplyInvalidLinkError("申请链接为空。")
	return parts[1]


def _blocked_text(status: str, author_name: str) -> str:
	if status == "blacklisted":
		return f"作者 {author_name} 已被禁止通过本 Bot 下载与分享，无法申请加入兽人作者名单。"
	if status == "already_furry":
		return f"作者 {author_name} 已在兽人作者名单中，无需申请。"
	return ""


async def edit_or_reply(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		text: str, *, reply_markup=None) -> None:
	"""优先编辑当前消息（保留上下文），失败时再补一条新消息。"""
	query = update.callback_query
	if query is not None:
		try:
			await query.edit_message_text(text, reply_markup=reply_markup)
			return
		except Exception:
			logger.debug("edit_message_text 失败，改为发送新消息", exc_info=True)
	await reply(update, context, text, reply_markup=reply_markup, delete_after=0)


async def apply_furry(update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""af：告知申请后果，并给出二次确认按钮。"""
	try:
		link = _link_from_data(data)
		inspection = await ApplyService().inspect(link)
	except ApplyInvalidLinkError:
		await edit_or_reply(update, context, "无法从链接中解析作者 ID。")
		return

	blocked = _blocked_text(inspection.status, inspection.author_name)
	if blocked:
		await edit_or_reply(update, context, blocked)
		return

	if inspection.status == "pending":
		await edit_or_reply(
			update, context,
			f"作者 {inspection.author_name}（#a{inspection.author_id}）的申请已在审核中\n"
			"请等待管理员核验")
		return

	await edit_or_reply(
		update, context,
		apply_notice(inspection.author_name, inspection.author_id),
		reply_markup=confirm_furry_keyboard(link))


async def apply_furry_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""afy：用户确认后写入申请记录，并把作品转入中转频道。"""
	user = update.effective_user
	if user is None:
		return

	try:
		link = _link_from_data(data)
	except ApplyInvalidLinkError:
		await edit_or_reply(update, context, "无法从链接中解析作者 ID。")
		return

	await edit_or_reply(update, context, "正在提交申请，请稍候……")

	try:
		result = await ApplyService().submit(
			link,
			user_id=user.id,
			user_name=f"{user.first_name} {user.last_name}",
			send_transit=lambda record: send_to_transit(update, context, record),
		)
	except ApplyInvalidLinkError:
		await edit_or_reply(update, context, "无法从链接中解析作者 ID。")
		return

	blocked = _blocked_text(result.status, result.author_name)
	if blocked:
		await edit_or_reply(update, context, blocked)
		return

	if result.status == "pending":
		await edit_or_reply(
			update, context,
			f"作者 {result.author_name}（#a{result.author_id}）的申请已在审核中，请勿重复提交")
		return

	message = [
		f"✅ 已提交兽人作者申请：", "",
		f"{result.author_name}（#a{result.author_id}）",
		f"管理员核验后会私聊通知结果"
	]
	await edit_or_reply(update, context, "\n".join(message))
