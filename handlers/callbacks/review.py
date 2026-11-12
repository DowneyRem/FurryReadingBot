"""管理侧核验 callback：rfy（通过）/ rfn（拒绝）。

审核状态与名单更新在 services.review_service；
本模块只负责中转消息、审核回执和私聊通知。

**拉黑不在这里**：核验裁决的是「这位用户替作者提的申请是否成立」，
不是「作者本人是否愿意被传播」。拉黑只能由作者本人的诉求触发，
入口等「作者申请下架」流程定下来再接（`services/takedown_service.py` 已备好）。
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.telegram import reply, transit_admin_policy
from services import ReviewDecision, ReviewResult, ReviewService
from utils.json import JsonDict


logger = logging.getLogger(__name__)


def applicant_text(record: JsonDict, *, approve: bool) -> str:
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
	text = []
	if result.status == "approved":
		text.append(f"🐺 #兽人作者申请已通过")
		text.append(f"✅ 通过：{result.author_name}（#a{result.author_id}）")
	else:
		text.append(f"🐺 #兽人作者申请已拒绝")
		text.append(f"❌ 拒绝：{result.author_name}（#a{result.author_id}）")

	record = result.record
	if record is not None:
		text.append(f"🈸 申请：{record.user_name}（#u{record.user_id}）")
	last_name = f"{user.last_name if user.last_name is not None else''}"
	text.append(f"👤 审核：{user.first_name} {last_name} （#u{user.id}）")
	return "\n".join(text)


async def review_application(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str, decision: ReviewDecision) -> None:
	"""rfy / rfn：核验申请并更新名单。"""
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
			))


async def apply_approve(update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""rfy：核验通过，加入兽人作者名单。"""
	await review_application(update, context, data=data, decision="approve")


async def apply_reject(update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""rfn：核验不通过，拒绝申请。"""
	await review_application(update, context, data=data, decision="reject")
