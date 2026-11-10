"""用户侧申请 callback：af（告知后果 + 二次确认）/ afy（提交申请）。

管理核验在 handlers.callbacks.review，公共工具在 handlers.callbacks.common。
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks._common import reply
from keyboards import confirm_author_keyboard
from sources import fetch
from storage.application import ApplicationStore
from storage.list import ListManager
from utils.links import get_id


logger = logging.getLogger(__name__)
_applications: ApplicationStore | None = None


def get_applications() -> ApplicationStore:
	global _applications
	if _applications is None:
		_applications = ApplicationStore()
	return _applications


def parse_apply_data(data: str) -> tuple[str, str]:
	"""拆出 callback_data 里的 link 与 author_id，形如 "af;{link};{author_id}"。"""
	parts = data.split(";")
	link = parts[1] if len(parts) > 1 else ""
	author_id = parts[2] if len(parts) > 2 else ""
	return link, author_id


def guess_kind(link: str) -> str:
	"""从链接猜申请对象类型，仅用于申请记录。"""
	if "/series/" in link:
		return "series"
	if "/novel/" in link or "/pn/" in link:
		return "novel"
	if "/user/" in link or "/pu/" in link:
		return "author"
	return ""


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


def forbid_reason(author_id: str, manager: ListManager) -> str:
	"""不可申请的原因；可以申请时返回空字符串。"""
	if manager.is_blacklisted(author_id):
		name = manager.blacklist.get_name(author_id) or author_id
		return f"作者 {name} 已被禁止通过本 Bot 下载与分享，无法申请加入兽人作者名单。"
	if manager.is_furryauthor(author_id):
		name = manager.furrylist.get_name(author_id) or author_id
		return f"作者 {name} 已在兽人作者名单中，无需申请。"
	return ""


async def lookup_author_name(link: str, author_id: str = "") -> str:
	"""从链接拉取作者名；失败时退回作者 ID。"""
	if link:
		try:
			item = await fetch(link)
			name = str(getattr(item, "author_name", "") or "")
			if name:
				return name
		except Exception:
			logger.warning("申请时拉取作者信息失败：%s", link, exc_info=True)
	return author_id


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
	link = data.split(";")[1]
	author_id = get_id(link)
	
	manager = ListManager()
	reason = forbid_reason(author_id, manager)
	if reason:
		await edit_or_reply(update, context, reason)
		return
	
	applications = get_applications()
	record = applications.get(author_id)
	if record and record.status == ApplicationStore.STATUS_PENDING:
		name = record.author_name or author_id
		await edit_or_reply(
			update, context,
			f"作者 {name}（#a{author_id}）的申请已在审核中\n请等待管理员核验")
		return
	
	author = await fetch(link)
	name = author.author_name
	await edit_or_reply(
		update, context,
		apply_notice(name, author_id),
		reply_markup=confirm_author_keyboard(link))


async def apply_furry_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""afy：用户确认后写入申请记录，并把作品转入中转频道。"""
	link = data.split(";")[1]
	author_id = get_id(link)
	
	manager = ListManager()
	reason = forbid_reason(author_id, manager)
	if reason:
		await edit_or_reply(update, context, reason)
		return
	
	applications = get_applications()
	record = applications.get(author_id)
	if record and record.status == ApplicationStore.STATUS_PENDING:
		name = record.author_name
		await edit_or_reply(
			update, context,
			f"作者 {name}（#a{author_id}）的申请已在审核中，请勿重复提交")
		return
	
	await edit_or_reply(update, context, "正在提交申请，请稍候……")
	
	author = await fetch(link)
	name = author.author_name
	user = update.effective_user
	record = applications.submit(
		author_id,
		author_name=name,
		link=link,
		kind=guess_kind(link),
		user_id=user.id,
		user_name=user.first_name,
	)
	logger.info(f"收到兽人作者申请：\n{record.author_name}=({record.author_id}) count={record.count} user={record.user_id}")

	# 用户确认后，相关小说转入中转频道，等待管理员人工核验
	await send_to_transit(update, context, record)
	message = [
		f"已提交兽人作者申请：",
		f"{record.author_name}（#a{author_id}）",
		f"管理员核验后会私聊通知结果"
	]
	await edit_or_reply(update, context, "\n".join(message))
