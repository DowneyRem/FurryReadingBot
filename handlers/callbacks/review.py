"""管理侧核验 callback：afa（通过）/ afr（拒绝）/ afb（拒绝并拉黑）。

用户侧申请在 handlers.callbacks.apply，公共工具在 handlers.callbacks._common。
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks.common import get_applications, reply
from storage.application import ApplicationStore
from storage.list import ListManager
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


async def review_application(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str, approve: bool, blacklist: bool = False) -> None:
	"""afa / afr / afb：在中转频道 / 测试频道里核验申请并更新名单。"""
	author_id = data.split(";")[1]
	user = update.effective_user
	applications = get_applications()
	record = applications.get(author_id)
	if record is None:
		await close_transit_message(update, context, f"申请记录不存在（#a{author_id}）")
		return
	if str(record.status or "") != ApplicationStore.STATUS_PENDING:
		# 重复点击 / 并发核验：保证审核只生效一次
		await close_transit_message(
			update, context,
			f"该申请已处理（{record.status or '未知'}）："
			f"{record.author_name or author_id}（#a{author_id}）")
		return

	manager = ListManager()
	name = record.author_name
	text = ["#兽人作者申请_已完成"]
	if approve:
		applications.set_status(author_id, ApplicationStore.STATUS_APPROVED)
		manager.add_furrylist(author_id, name=name, note="兽人作者申请通过")
		text.append(f"✅ 通过：{name}（#a{author_id}）")
	else:
		applications.set_status(author_id, ApplicationStore.STATUS_REJECTED)
		if blacklist:
			manager.add_blacklist(author_id, name=name, note="申请核验未通过")
			text.append(f"🚫 拒绝并拉黑：{name}（#a{author_id}）")
		else:
			text.append(f"🈲 拒绝：{name}（#a{author_id}）")
	text.append(f"🈸 申请：{record.user_name}（#u{record.user_id}）")
	text.append(f"👤 审核：{user.first_name} {user.last_name}（#u{user.id}）")

	logger.info(f"申请核验 {author_id=} {approve=} {blacklist=}")
	await close_transit_message(update, context, "\n".join(text))
	await notify_applicant(
		context, record,
		applicant_text(record, approve=approve, blacklist=blacklist))


async def apply_approve(update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""afa：核验通过，加入兽人作者名单。"""
	await review_application(update, context, data=data, approve=True)


async def apply_reject(update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""afr：核验不通过，拒绝申请。"""
	await review_application(update, context, data=data, approve=False)


async def apply_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""afb：核验不通过并拉黑作者。"""
	await review_application(update, context, data=data, approve=False, blacklist=True)
