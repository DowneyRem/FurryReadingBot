"""作者侧下架申请 callback：ab（告知后果 + 确认）/ aby（受理，回材料清单）/ abn（取消）。

管理侧核验：ablock（拉黑）/ abdeny（拒绝）。
业务规则在 services.blacklist_service；本模块只负责 Telegram 展示、
删中转卡片和私聊通知。核验通过只更新名单，不删除历史分享。
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks.apply import edit_or_reply
from handlers.callbacks.review import close_transit_message, notify_applicant
from handlers.telegram import transit_admin_policy
from keyboards import confirm_black_keyboard
from services import (
	BlacklistDecision,
	BlacklistReview,
	BlacklistService,
	DownloadService,
)
from storage.black_request import BlacklistRequestStore
from utils.links import get_id


logger = logging.getLogger(__name__)

BLACKLIST_NOTICE = "\n".join([
	"申请把该作者加入黑名单前，请先确认：", "",
	"1. 只有作者本人可以发起下架申请",
	"2. 需要提交能证明你是该作者的截图（Pixiv 后台投稿管理页）",
	"3. 审核通过后，该作者的作品不能再被下载或分享",
	"4. 申请需要管理员人工核验，核验期间仍可能被分享", "",
	"确认发起申请吗？",
])


def material_notice(author_name: str, author_id: str) -> str:
	"""受理成功后，告诉作者要提交什么材料。"""
	return "\n".join([
		f"已受理：{author_name}（#a{author_id}）的下架申请",
		"",
		"请把下列材料以图片形式发给我：",
		"1. Pixiv 后台「作品管理」或「投稿一览」截图",
		"2. 截图里能看到该账号与至少一个作品标题",
		"",
		f"请在 {BlacklistRequestStore.MATERIAL_TTL_MINUTES} 分钟内发送；管理员核验后会私聊通知结果。",
	])


def review_receipt(result: BlacklistReview, user) -> str:
	"""中转频道的核验回执。"""
	text = []
	if result.status == "approved":
		text.append("#作者下架申请已拉黑")
		text.append(f"🚫 已拉黑：{result.author_name}（#a{result.author_id}）")
	else:
		text.append("#作者下架申请已拒绝")
		text.append(f"❌ 已拒绝：{result.author_name}（#a{result.author_id}）")

	record = result.record
	if record is not None:
		text.append(f"🈸 申请：{record.user_name}（#u{record.user_id}）")
	text.append(f"👤 审核：{user.first_name} {user.last_name}（#u{user.id}）")
	return "\n".join(text)


def applicant_text(result: BlacklistReview) -> str:
	"""私聊通知申请人的文案。"""
	message = []
	if result.status == "approved":
		message.extend(["✅ 你提交的小说下架申请已通过", ""])
		message.append(f"作者：{result.author_name}（#a{result.author_id}）")
		message.append(f"该作者已加入黑名单，之后不会再被下载或分享")
	else:
		message.extend(["❌ 你提交的小说下架申请未通过", ""])
		message.append(f"作者：{result.author_name}（#a{result.author_id}）")
		message.append(f"如有疑问，可以联系管理员")
	return "\n".join(message)


def _link_from_data(data: str) -> str:
	parts = data.split(";", 1)
	return parts[1].strip() if len(parts) > 1 else ""


async def _author_name(link: str) -> str:
	"""抓一次作者名，失败就留空（回落到名单里的名字或作者 ID）。"""
	try:
		offer = await DownloadService().inspect_link(link)
		return offer.author_name
	except Exception:
		logger.warning("抓取作者信息失败：%s", link, exc_info=True)
		return ""


async def request_blacklist(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""ab：告知下架申请的后果，并给出二次确认。"""
	link = _link_from_data(data)
	author_id = get_id(link)
	if not author_id:
		await edit_or_reply(update, context, "无法从链接中解析作者 ID。")
		return

	await edit_or_reply(
		update, context, BLACKLIST_NOTICE,
		reply_markup=confirm_black_keyboard(link))


async def request_blacklist_confirm(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""aby：受理申请，回材料清单。"""
	link = _link_from_data(data)
	author_id = get_id(link)
	user = update.effective_user
	if not author_id or user is None:
		await edit_or_reply(update, context, "无法从链接中解析作者 ID。")
		return

	await edit_or_reply(update, context, "正在受理申请，请稍候……")

	result = BlacklistService().request(
		author_id,
		author_url=link,
		author_name=await _author_name(link),
		user_id=user.id,
		user_name=f"{user.first_name} {user.last_name}".strip(),
	)
	if result.status == "already_blacklisted":
		await edit_or_reply(
			update, context,
			f"作者 {result.author_name} 已停止分享，无需申请下架。")
		return
	if result.status == "pending_review":
		await edit_or_reply(
			update, context,
			f"作者 {result.author_name} 的下架申请已在核验中\n请等待管理员处理。")
		return

	await edit_or_reply(
		update, context, material_notice(result.author_name, author_id))


async def review_blacklist(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str, decision: BlacklistDecision) -> None:
	"""ablock / abdeny：中转频道管理员核验下架申请。"""
	author_id = _link_from_data(data)
	user = update.effective_user
	if user is None:
		return

	admin = await transit_admin_policy(context.bot).check(user.id)
	if not admin.allowed:
		logger.warning(
			"非管理员尝试核验下架申请 author=%s user=%s",
			author_id or "-", user.id)
		await close_transit_message(
			update, context, "仅中转频道管理员可以核验申请")
		return

	if not author_id:
		await close_transit_message(update, context, "申请参数不完整")
		return

	result = BlacklistService().review(author_id, decision)
	if result.status == "missing":
		await close_transit_message(
			update, context, f"申请记录不存在（#a{author_id}）")
		return
	if result.status == "already_processed":
		await close_transit_message(
			update, context,
			f"该申请已处理：{result.author_name}（#a{author_id}）")
		return

	await close_transit_message(update, context, review_receipt(result, user))
	if result.record is not None:
		await notify_applicant(context, result.record, applicant_text(result))


async def blacklist_approve(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""ablock：核验通过，加入黑名单。"""
	await review_blacklist(update, context, data=data, decision="approve")


async def blacklist_reject(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""abdeny：核验不通过，拒绝下架申请。"""
	await review_blacklist(update, context, data=data, decision="reject")
