"""分享类 callback（Telegram 展示层）。

用户侧：snp / sna / snn（公开 / 私密 / 拒绝分享）。
中转频道：cfy（放行到兽人小说频道）/ cfn（不通过，结掉卡片）。
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import FURRY_NOVELS
from handlers.callbacks.download import forbidden_text
from handlers.callbacks.review import close_transit_message, ensure_transit_admin
from handlers.telegram import reply, upload_file
from keyboards import check_furry_keyboard, import_to_legado_keyboard
from policy.author import AuthorPolicy
from services import ShareRequest, ShareResult, ShareService
from services.share_service import TRANSIT_NOTICE
from sources import resolve_source
from storage.file_cache import FileCacheStore, get_file_cache
from storage.share_records import get_share_records
from utils.links import get_id


logger = logging.getLogger(__name__)


def format_remaining(seconds: float) -> str:
	"""把剩余冷却秒数格式化为「x 天 y 小时」/「x 小时 y 分钟」。"""
	minutes = int(seconds // 60) + (1 if seconds % 60 else 0)
	days, minutes = divmod(minutes, 24 * 60)
	hours, minutes = divmod(minutes, 60)
	if days:
		return f"{days} 天 {hours} 小时" if hours else f"{days} 天"
	if hours:
		return f"{hours} 小时 {minutes} 分钟" if minutes else f"{hours} 小时"
	return f"{max(minutes, 1)} 分钟"


def format_channels(channels: tuple[str, ...]) -> str:
	"""把目标频道拼成展示文案；没配频道时给一个兜底词。"""
	return "、".join(channels) if channels else "频道"


def shared_text(result: ShareResult, *, public: bool) -> str:
	if result.transit:
		text = f"暂时无法判断是否为兽人小说\n现已转入中转频道 {format_channels(result.channels)}\n等待核验"
	else:
		text = f"已经{'公开' if public else '匿名'}分享至 {format_channels(result.channels)}"
	if result.failed_channels:
		text += f"\n{format_channels(result.failed_channels)} 发送失败"
	return text


async def share(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str, public: bool) -> ShareResult | None:
	"""把缓存中的文件分享到目标频道：成功返回结果，失败返回 None。"""
	parts = data.split(";")
	# data 如 "snp;{kind};{item_id};{file_type}"
	if len(parts) < 3:
		await reply(update, context, "分享参数不完整")
		return None

	kind, item_id = parts[1], parts[2]
	file_type = parts[3] if len(parts) > 3 else "txt"
	query = update.callback_query
	user = query.from_user if query else None
	user_name = f"{user.first_name} {user.last_name if user.last_name else ''}".strip() if user else ""
	request = ShareRequest(
		kind=kind,
		item_id=item_id,
		file_type=file_type,
		public=public,
		user_id=user.id if user else None,
		user_name=user_name,
	)

	async def send(artifact, chat_id: str) -> int:
		"""发到一个频道：中转挂核验键盘，正式频道挂开源阅读键盘。"""
		markup = (
			check_furry_keyboard(artifact.link)
			if artifact.transit
			else import_to_legado_keyboard(artifact.link)
		)
		sent = await upload_file(
			update, context,
			file_id=artifact.file_id,
			filename=artifact.filename,
			chat_id=chat_id,
			caption=artifact.caption,
			reply_markup=markup,
		)
		return sent.message_id

	result = await ShareService().share(request, upload=send)
	if result.status == "inflight":
		await reply(update, context, "该作品正在分享中，请稍候再试")
		return None
	if result.status == "cooldown":
		await reply(
			update, context,
			f"该作品刚刚已经分享过，{format_remaining(result.remaining_seconds)}后可再次分享")
		return None
	if result.status == "cache_missing":
		await reply(update, context, "缓存已失效，请重新下载后再分享")
		return None
	if result.status == "forbidden":
		await reply(update, context, forbidden_text(result.author_status, result.author_name))
		return None
	if result.status == "no_channel":
		await reply(
			update, context,
			"未配置中转频道" if result.transit else "未配置分享频道")
		return None
	if result.status == "failed":
		await reply(update, context, "分享失败，请稍后重试")
		return None
	return result


async def share_public(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	result = await share(update, context, data=data, public=True)
	if result is not None:
		await reply(update, context, shared_text(result, public=True))


async def share_private(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	result = await share(update, context, data=data, public=False)
	if result is not None:
		await reply(update, context, shared_text(result, public=False))


async def share_reject(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	query = update.callback_query
	if query is not None:
		await query.edit_message_reply_markup(reply_markup=None)


# ----- 中转频道核验：cfy / cfn -----
def official_caption(caption: str) -> str:
	"""去掉中转 caption 顶部的「待核验」提示，得到正式频道用的文案。"""
	text = (caption or "").strip()
	if text.startswith(TRANSIT_NOTICE):
		text = text[len(TRANSIT_NOTICE):].lstrip("\n")
	return text


def link_from_data(data: str) -> str:
	"""解析 `cfy;{link}` / `cfn;{link}` 里的作品链接。"""
	parts = data.split(";", 1)
	return parts[1].strip() if len(parts) > 1 else ""


def work_from_link(link: str) -> tuple[str, str] | None:
	"""作品链接 → (kind, item_id)；来源不认识 / 解析不出 id 时返回 None。"""
	source = resolve_source(link)
	if source is None:
		return None
	if source.is_series_link(link):
		kind = "series"
	elif source.is_novel_link(link):
		kind = "novel"
	elif source.is_author_link(link):
		kind = "author"
	else:
		return None
	item_id = get_id(link)
	return (kind, item_id) if item_id else None


def transit_receipt(
		*, approved: bool, link: str, user) -> str:
	"""结掉中转卡片后，留在频道里的回执。"""
	lines = [
		"✅ #兽人小说已放行" if approved else "❌ #兽人小说未通过",
		f"🔗 {link}" if link else "🔗 （链接缺失）",
	]
	if user is not None:
		user_name = f"{user.first_name} {user.last_name if user.last_name else ''}".strip()
		lines.append(f"👤 操作人：{user_name}（#u{user.id}）")
	return "\n".join(lines)


def drop_transit_record(
		kind: str, item_id: str, author_id: str, message) -> None:
	"""卡片即将删除：先把这条中转消息从分享记录里摘掉。

	不摘的话，作者日后被下架时 `TakedownService` 会去删一条已经删掉的消息，
	在回执里留下永远失败的「删除失败」。
	"""
	if message is None or not author_id:
		return
	chat_id = getattr(message, "chat_id", None)
	message_id = getattr(message, "message_id", None)
	if not chat_id or not message_id:
		return
	get_share_records().remove_message(
		author_id, kind, item_id, chat_id, message_id)


async def share_transit_approve(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""cfy：把中转卡片里的作品发到兽人小说频道，并结掉卡片。"""
	if not await ensure_transit_admin(update, context, "cfy"):
		return

	link = link_from_data(data)
	work = work_from_link(link)
	if work is None:
		await close_transit_message(update, context, "链接无法解析，未转发")
		return
	kind, item_id = work

	# 分享按钮只挂在 txt 上，中转卡片也只会是 txt
	cached = get_file_cache().get_valid(
		FileCacheStore.make_key(kind, item_id, "txt"))
	if not cached:
		await close_transit_message(
			update, context, "缓存已失效，无法转发；请让分享者重新下载后再分享")
		return
	if not AuthorPolicy().check(cached.author_id, cached.author_name).can_download:
		await close_transit_message(update, context, "该作者当前已不可分享，未转发")
		return
	if not FURRY_NOVELS:
		await close_transit_message(update, context, "未配置兽人小说频道")
		return

	query = update.callback_query
	message = query.message if query else None
	caption = official_caption(getattr(message, "caption", "") or "")
	try:
		sent = await upload_file(
			update, context,
			file_id=cached.file_id,
			filename=cached.file_name or None,
			chat_id=FURRY_NOVELS,
			caption=caption,
			reply_markup=import_to_legado_keyboard(str(cached.link or "")),
		)
	except Exception:
		logger.exception("中转放行转发失败 %s:%s", kind, item_id)
		await close_transit_message(
			update, context, "转发到兽人小说频道失败，请稍后重试")
		return

	# 正式频道的消息也要进分享记录，作者下架时才删得到
	get_share_records().record(
		author_id=cached.author_id,
		author_name=cached.author_name,
		kind=kind,
		item_id=item_id,
		messages=[(FURRY_NOVELS, sent.message_id)],
		title=(caption.splitlines()[0] if caption else ""),
	)
	drop_transit_record(kind, item_id, str(cached.author_id or ""), message)
	await close_transit_message(
		update, context,
		transit_receipt(
			approved=True, link=link, user=update.effective_user))


async def share_transit_reject(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	"""cfn：不通过，结掉中转卡片，不发布到正式频道。"""
	if not await ensure_transit_admin(update, context, "cfn"):
		return

	link = link_from_data(data)
	work = work_from_link(link)

	query = update.callback_query
	message = query.message if query else None
	if work is not None:
		kind, item_id = work
		cached = get_file_cache().get_valid(
			FileCacheStore.make_key(kind, item_id, "txt"))
		drop_transit_record(
			kind, item_id,
			str(cached.author_id or "") if cached else "",
			message)
	await close_transit_message(
		update, context,
		transit_receipt(
			approved=False, link=link, user=update.effective_user))
