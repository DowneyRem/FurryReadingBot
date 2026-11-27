"""作者相关命令：`/black` 申请下架、`/furry` 申请加入兽人作者名单，
以及管理员快捷方式 `/blackadd`、`/furryadd`。

前两个命令共用同一套参数解析（作者 ID 或作者主页链接）；后续流程分别复用
`handlers.callbacks.blacklist`（材料 → 送审 → 核验）与
`handlers.callbacks.apply`（后果告知 → 确认 → 送审）。

`/furryadd`、`/blackadd` 强制校验中转频道管理员；通过后不做任何前置要求
（不要截图、不二次确认、不写申请记录），直接写 `data/*.json`，
再把与核验通过一致的回执留在中转频道。
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks.apply import apply_furry
from handlers.callbacks.blacklist import (
	BLACKLIST_NOTICE,
	review_receipt,
	takedown_history,
	takedown_notice,
)
from handlers.callbacks.review import receipt_text
from handlers.telegram import send_transit_message, transit_admin_policy
from keyboards import confirm_black_keyboard, retry_takedown_keyboard
from services import BlacklistReview, ReviewResult
from sources import fetch, resolve_source
from sources.errors import SourceError
from sources.pixiv.urls import url_author
from storage import get_lists
from utils.links import get_id


logger = logging.getLogger(__name__)


BLACK_USAGE = "\n".join([
	"发送 Pixiv 或 Linpx 作者主页链接即可申请下架",
	"如：https://www.pixiv.net/users/12345",
	"也可以发送作者 ID 或使用命令：/black 12345",
])

FURRY_USAGE = "\n".join([
	"发送 Pixiv 或 Linpx 作者主页链接即可申请加入兽人作者名单",
	"如：https://www.pixiv.net/users/12345",
	"也可以发送作者 ID 或使用命令：/furry 12345",
])

# 管理员快捷方式：参数解析与 /black、/furry 完全一致，只是跳过申请 / 核验流程
ADMIN_DENIED = "⚠️ 仅中转频道管理员可以直接修改名单"
ADD_FURRY_USAGE = "用法：/furryadd 作者 ID 或主页链接（仅中转频道管理员）"
ADD_BLACK_USAGE = "用法：/blackadd 作者 ID 或主页链接（仅中转频道管理员）"
# 名单 note：与走流程写下的「兽人作者申请通过」/「作者本人申请下架」区分开
FURRY_NOTE = "管理员直接添加"
BLACK_NOTE = "管理员直接拉黑"


def _author_link(arg: str) -> str:
	"""把 /black、/furry、/blackadd、/furryadd 的参数归一化成 Pixiv 作者主页链接。"""
	value = (arg or "").strip()
	if not value:
		return ""
	if value.isdigit():
		return url_author(value)
	source = resolve_source(value)
	if source is None or not source.is_author_link(value):
		return ""
	author_id = get_id(value)
	return url_author(author_id) if author_id else ""


async def black(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/black：带作者 ID / 主页链接时给出下架确认键盘，否则回用法提示。"""
	message = update.effective_message
	if message is None:
		return

	args = context.args or []
	link = _author_link(args[0]) if args else ""
	if not link:
		await message.reply_text(BLACK_USAGE, disable_web_page_preview=True)
		return

	await message.reply_text(
		BLACKLIST_NOTICE,
		reply_markup=confirm_black_keyboard(link),
		disable_web_page_preview=True,
	)


async def furry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/furry：带作者 ID / 主页链接时给出兽人作者申请确认键盘。"""
	message = update.effective_message
	if message is None:
		return

	args = context.args or []
	link = _author_link(args[0]) if args else ""
	if not link:
		await message.reply_text(FURRY_USAGE, disable_web_page_preview=True)
		return

	try:
		# 复用按钮入口：已拉黑 / 已在名单 / 审核中的状态检查都在这里
		await apply_furry(update, context, data=f"af;{link}")
	except SourceError as e:
		await message.reply_text(str(e))
	except Exception:
		logger.exception("兽人作者申请检查失败 link=%s", link)
		await message.reply_text(
			"获取作者信息失败，请稍后再试，或直接发送作者主页链接。")


async def _ensure_admin(
		update: Update, context: ContextTypes.DEFAULT_TYPE, command: str) -> bool:
	"""快捷方式的强制校验：非管理员只回一句拒绝，不透露参数用法。"""
	message = update.effective_message
	user = update.effective_user
	if message is None or user is None:
		return False

	decision = await transit_admin_policy(context.bot).check(user.id)
	if decision.allowed:
		return True

	logger.warning(
		"非管理员尝试执行 %s user=%s status=%s",
		command, user.id, decision.status)
	await message.reply_text(
		"无法确认你的管理员身份，请稍后重试"
		if decision.status is None else ADMIN_DENIED)
	return False


async def _author_name(link: str) -> str:
	"""抓一次作者名；失败只记日志（写名单不依赖网络，名单允许只记 ID）。"""
	try:
		author = await fetch(link)
		return str(getattr(author, "author_name", "") or "")
	except Exception:
		logger.warning("抓取作者信息失败 link=%s", link, exc_info=True)
		return ""


async def add_furry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/furryadd：管理员直接把作者写进兽人作者名单，回执留在中转频道。"""
	if not await _ensure_admin(update, context, "/furryadd"):
		return
	message = update.effective_message
	user = update.effective_user
	if message is None or user is None:
		return
	args = context.args or []
	link = _author_link(args[0]) if args else ""
	if not link:
		await message.reply_text(ADD_FURRY_USAGE)
		return

	# 不做任何前置要求：不写申请记录、不占冷却，直接写名单
	author_id = get_id(link)
	name = await _author_name(link)
	lists = get_lists()
	if lists.is_blacklisted(author_id):
		await message.reply_text(
			f"作者 {name or author_id}（#a{author_id}）已在黑名单中，未写入\n"
			"黑名单优先于兽人作者名单：如需放行，请先把作者移出黑名单")
		return
	if lists.is_furryauthor(author_id):
		await message.reply_text(
			f"作者 {lists.furrylist.get_name(author_id) or name or author_id}"
			f"（#a{author_id}）已在兽人作者名单中，未重复写入")
		return

	lists.add_furrylist(author_id, name=name, note=FURRY_NOTE)
	# 回执复用核验通过的 receipt_text（没有申请记录，会自动省掉「🈸 申请」那行），
	# 末尾加一行尾注，标明这次是管理员直接加的
	receipt = receipt_text(
		ReviewResult("approved", author_id, name or author_id), user)
	receipt += f"\n🛡 {FURRY_NOTE}"
	sent = await send_transit_message(context, receipt)
	lines = [f"✅ 已加入兽人作者名单：{name or author_id}（#a{author_id}）"]
	if not name:
		lines.append("⚠️ 没抓到作者名，名单里暂时只记了 ID")
	lines.append(
		"中转频道已留下回执" if sent
		else "⚠️ 中转频道回执发送失败，请检查 TRANSIT_CHANNEL")
	await message.reply_text("\n".join(lines))


async def add_black(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/blackadd：管理员直接把作者写进黑名单，并下架频道里的历史分享。"""
	if not await _ensure_admin(update, context, "/blackadd"):
		return
	message = update.effective_message
	user = update.effective_user
	if message is None or user is None:
		return
	args = context.args or []
	link = _author_link(args[0]) if args else ""
	if not link:
		await message.reply_text(ADD_BLACK_USAGE)
		return

	author_id = get_id(link)
	name = await _author_name(link)
	lists = get_lists()
	if lists.is_blacklisted(author_id):
		await message.reply_text(
			f"作者 {lists.blacklist.get_name(author_id) or name or author_id}"
			f"（#a{author_id}）已在黑名单中，未重复写入")
		return

	# 与核验通过一致：先移出兽人名单再加黑；写盘后再删历史分享，
	# 删除失败不回头改名单，回执上给「重试删除」入口
	lists.remove_furrylist(author_id)
	lists.add_blacklist(author_id, name=name, note=BLACK_NOTE)
	takedown = await takedown_history(context, author_id)
	notice = takedown_notice(takedown)
	retry = retry_takedown_keyboard(author_id) if takedown.failed else None
	# 回执复用核验通过的 review_receipt（含「🗑️ 已删除」、省掉「🈸 申请人」），
	# 末尾加一行尾注，标明这次是管理员直接拉黑的
	receipt = review_receipt(
		BlacklistReview("approved", author_id, name or author_id), user, takedown)
	receipt += f"\n🛡 {BLACK_NOTE}"
	sent = await send_transit_message(context, receipt, reply_markup=retry)

	lines = [f"✅ 已加入黑名单：{name or author_id}（#a{author_id}）"]
	if not name:
		lines.append("⚠️ 没抓到作者名，名单里暂时只记了 ID")
	if notice:
		lines.append(notice)
	if not sent:
		lines.append("⚠️ 中转频道回执发送失败，请检查 TRANSIT_CHANNEL")
	await message.reply_text("\n".join(lines))
