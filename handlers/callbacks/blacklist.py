"""作者侧下架申请 callback：ab（告知后果 + 确认）/ aby（受理，回材料清单）/ ba（返回）。

管理侧核验：rby（拉黑）/ rbn（拒绝）。
业务规则在 services.blacklist_service；本模块只负责 Telegram 展示、
删中转卡片和私聊通知。核验通过 = 更新名单 + 下架频道里的历史分享
（删除通过 `handlers.telegram.takedown · takedown_author` 注入）。
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks.apply import edit_or_reply
from handlers.callbacks.review import close_transit_message, notify_applicant
from handlers.telegram import takedown_author, transit_admin_policy
from keyboards import confirm_black_keyboard
from services import (
	BlacklistDecision,
	BlacklistReview,
	BlacklistService,
	DownloadService,
	TakedownResult,
)
from storage.black_request import BlackRequestStore
from utils.links import get_id


logger = logging.getLogger(__name__)

BLACKLIST_NOTICE = "\n".join([
	"申请把该作者加入黑名单前，请先确认：", "",
	"1. 只有作者本人可以发起下架申请",
	"2. 需要提交能证明你是该作者的截图（Pixiv 后台截图）",
	"3. 申请需要管理员人工核验，核验期间仍可能被分享",
	"4. 审核通过后，该作者的作品不能再被下载或分享",
	"5. 申请通过后，频道里的分享内容也会一并被删除",
	"",
	"确认发起申请吗？",
])


def material_notice(author_name: str, author_id: str) -> str:
	"""受理成功后，告诉作者要提交什么材料。"""
	return "\n".join([
		f"请把 {author_name} 的「Pixiv 后台数据」截图并以图片形式发给我：",
		"",
		"1. 截图位置为 Pixiv 的「数据分析」或「我的作品」页面",
		"2. 截图里要有：该作者的至少一篇小说",
		"",
		f"请在 {BlackRequestStore.MATERIAL_TTL_MINUTES} 分钟内发送；管理员核验后会私聊通知结果",
	])


def takedown_notice(takedown: TakedownResult | None) -> str:
	"""下架结果摘要；None 表示这次没执行下架，不占用回执篇幅。"""
	if takedown is None:
		return ""
	# if takedown.total == 0:
	# 	return "🔊 频道里没有该作者的历史分享"
	lines = [f"🗑️ 已删除：{takedown.deleted} 条历史分享"]
	if takedown.skipped:
		lines.append(f"⚠️ {takedown.skipped} 条旧记录没有消息 ID，需手工处理")
	if takedown.failed:
		lines.append(f"❌ {takedown.failed} 条删除失败，记录已保留可重试")
	return "\n".join(lines)


def review_receipt(
		result: BlacklistReview,
		user,
		takedown: TakedownResult | None = None) -> str:
	"""中转频道的核验回执。"""
	text = []
	if result.status == "approved":
		text.append("🈲 #作者下架申请已通过")
		text.append(f"🚫 已下架：{result.author_name}（#a{result.author_id}）")
	else:
		text.append("🈲 #作者下架申请已拒绝")
		text.append(f"❌ 已拒绝：{result.author_name}（#a{result.author_id}）")

	notice = takedown_notice(takedown)
	if notice:
		text.append(notice)
	record = result.record
	if record is not None:
		text.append(f"🈸 申请人：{record.user_name}（#u{record.user_id}）")
	text.append(f"👤 审核人：{user.first_name} {user.last_name}（#u{user.id}）")
	return "\n".join(text)


def applicant_text(
		result: BlacklistReview,
		takedown: TakedownResult | None = None) -> str:
	"""私聊通知申请人的文案。"""
	message = []
	if result.status == "approved":
		message.extend(["✅ 你提交的下架小说申请已通过", ""])
		message.append(f"作者：{result.author_name}（#a{result.author_id}）")
		message.append(f"该作者已加入黑名单，之后不会再被下载或分享")
		if takedown is not None and takedown.deleted:
			message.append(f"频道中的历史分享已删除 {takedown.deleted} 条")
	else:
		message.extend(["❌ 你提交的下架小说申请未通过", ""])
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
			f"作者 {result.author_name}（#a{result.author_id}）的下架申请已在核验中\n请等待管理员处理。")
		return

	await edit_or_reply(
		update, context, material_notice(result.author_name, author_id))


async def _takedown(
		context: ContextTypes.DEFAULT_TYPE,
		author_id: str) -> TakedownResult | None:
	"""拉黑后下架频道里的历史分享；删除失败只记日志，不影响拉黑结果。"""
	try:
		result = await takedown_author(context, author_id)
	except Exception:
		logger.warning("下架历史分享失败 author=%s", author_id, exc_info=True)
		return None
	logger.info(
		"历史分享下架完成 author=%s deleted=%s skipped=%s failed=%s",
		author_id, result.deleted, result.skipped, result.failed)
	return result


async def review_blacklist(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str, decision: BlacklistDecision) -> None:
	"""rby / rbn：中转频道管理员核验下架申请。"""
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

	# 拉黑成功后再下架：名单已写盘，删除失败不回头改状态
	takedown = None
	if result.status == "approved":
		takedown = await _takedown(context, author_id)

	await close_transit_message(
		update, context, review_receipt(result, user, takedown))
	if result.record is not None:
		await notify_applicant(
			context, result.record, applicant_text(result, takedown))


async def blacklist_approve(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""rby：核验通过，加入黑名单。"""
	await review_blacklist(update, context, data=data, decision="approve")


async def blacklist_reject(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""rbn：核验不通过，拒绝下架申请。"""
	await review_blacklist(update, context, data=data, decision="reject")
