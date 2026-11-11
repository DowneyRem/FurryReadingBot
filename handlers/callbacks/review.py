"""管理侧核验 callback：afa（通过）/ afr（拒绝）/ afb（拒绝并拉黑）。

审核状态与名单更新在 services.review_service；
本模块只负责中转消息、审核回执和私聊通知。
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.telegram import reply, transit_admin_policy
from services import ReviewDecision, ReviewResult, ReviewService
from utils.json import JsonDict


logger = logging.getLogger(__name__)


def applicant_text(record: JsonDict, *, approve: bool, blacklist: bool = False) -> str:
	"""核验结果通知申请人的文案。"""
	message = []
	if approve:
		message.extend(["✅ 你提交的兽人作者申请已通过", ""])
		message.append(f"作者：{record.author_name}（#a{record.author_id}）")
		message.append("现在可以重新发送链接，下载并分享该作者的小说了")
	else:
		message.extend(["❌ 你提交的兽人作者申请未通过", ""])
		message.append(f"作者：{record.author_name}（#a{record.author_id}）")
		message.append("如有疑问，可以联系管理员")
	if blacklist:
		message.append("⚠️ 该作者已被禁止通过本 Bot 下载与分享")
	return "\n".join(message)


async def notify_applicant(
		context: ContextTypes.DEFAULT_TYPE, record: JsonDict, text: str) -> None:
	"""把核验结果私聊通知申请人，失败只记日志。"""
	user_id = str(record.user_id or "")
	if not user_id.isdigit():
		return
	try:
		await context.bot.send_message(chat_id=int(user_id), text=text)
	except Exception:
		logger.warning("通知申请人失败 user=%s", user_id, exc_info=True)


async def close_transit_message(
		update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
	"""删除中转消息，并把审核结果留在频道里。"""
	query = update.callback_query
	message = query.message
	if message is None:
		await reply(update, context, text, delete_after=8)
		return

	try:
		await message.delete()
	except Exception:
		logger.warning("删除中转消息失败", exc_info=True)

	chat_id = getattr(message, "chat_id", None)
	if chat_id:
		try:
			await context.bot.send_message(chat_id=chat_id, text=text)
		except Exception:
			logger.warning("审核回执发送失败", exc_info=True)


def _author_id_from_data(data: str) -> str:
	parts = data.split(";", 1)
	if len(parts) < 2:
		return ""
	return parts[1].strip()


def _receipt_text(result: ReviewResult, user) -> str:
	author_id = result.author_id
	name = result.author_name or author_id
	text = ["#兽人作者申请已完成"]
	if result.status == "approved":
		text.append(f"✅ 通过：{name}（#a{author_id}）")
	elif result.blacklisted:
		text.append(f"🚫 拒绝并拉黑：{name}（#a{author_id}）")
	else:
		text.append(f"🈲 拒绝：{name}（#a{author_id}）")

	record = result.record
	if record is not None:
		text.append(f"🈸 申请：{record.user_name}（#u{record.user_id}）")
	text.append(f"👤 审核：{user.first_name} {user.last_name}（#u{user.id}）")
	return "\n".join(text)


async def review_application(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str, decision: ReviewDecision) -> None:
	"""afa / afr / afb：核验申请并更新名单。"""
	author_id = _author_id_from_data(data)
	user = update.effective_user
	if user is None:
		return

	admin = await transit_admin_policy(context.bot).check(user.id)
	if not admin.allowed:
		logger.warning(
			"非管理员尝试核验申请 author=%s user=%s", author_id or "-", user.id)
		await close_transit_message(update, context, "仅中转频道管理员可以核验申请")
		return

	if not author_id:
		await close_transit_message(update, context, "申请参数不完整")
		return

	result = ReviewService().review(
		author_id,
		decision,
		reviewer_id=user.id,
		reviewer_name=f"{user.first_name} {user.last_name}",
	)

	if result.status == "missing":
		await close_transit_message(
			update, context, f"申请记录不存在（#a{author_id}）")
		return
	if result.status == "already_processed":
		await close_transit_message(
			update, context,
			f"该申请已处理（{result.previous_status or '未知'}）："
			f"{result.author_name}（#a{author_id}）")
		return

	await close_transit_message(update, context, _receipt_text(result, user))
	if result.record is not None:
		await notify_applicant(
			context, result.record,
			applicant_text(
				result.record,
				approve=result.status == "approved",
				blacklist=result.blacklisted,
			))


async def apply_approve(update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""afa：核验通过，加入兽人作者名单。"""
	await review_application(update, context, data=data, decision="approve")


async def apply_reject(update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""afr：核验不通过，拒绝申请。"""
	await review_application(update, context, data=data, decision="reject")


async def apply_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""afb：核验不通过并拉黑作者。"""
	await review_application(update, context, data=data, decision="blacklist")
