"""分享类 callback：snp / sna / snn。"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks._common import reply
from handlers.callbacks.upload import upload_file, get_cache
from storage.file_cache import FileCacheStore
from storage.share_record import ShareRecordStore
from config import (
	FURRY_READING, FURRY_NOVELS, FURRY_READING_NEW_GROUP, TEST_CHANNEL,
	SHARE_COOLDOWN_DAYS,
)


logger = logging.getLogger(__name__)
_share_records: ShareRecordStore | None = None
# 正在发送中的作品 key，避免并发点击造成重复分享
_inflight: set[str] = set()


def get_share_records() -> ShareRecordStore:
	global _share_records
	if _share_records is None:
		_share_records = ShareRecordStore(cooldown_days=SHARE_COOLDOWN_DAYS)
	return _share_records


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


async def share(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str, public: bool) -> bool:
	"""把缓存中的文件分享到目标频道：成功返回 True，失败返回 False。"""
	parts = data.split(";")
	# data 如 "snp;{kind};{item_id};{file_type}"
	if len(parts) < 3:
		await reply(update, context, "分享参数不完整")
		return False

	kind, item_id = parts[1], parts[2]
	file_type = parts[3] if len(parts) > 3 else "txt"
	cache_key = FileCacheStore.make_key(kind, item_id, file_type)

	# 分享冷却：同一部作品（kind:id）在冷却时间内不再重复发送
	records = get_share_records()
	share_key = ShareRecordStore.make_key(kind, item_id)
	if share_key in _inflight:
		await reply(update, context, "该作品正在分享中，请稍候再试")
		return False
	left = records.remaining(share_key)
	if left > 0:
		await reply(
			update, context,
			f"该作品刚刚已经分享过，{format_remaining(left)}后可再次分享")
		return False

	cached = get_cache().get_valid(cache_key)
	if not cached:
		await reply(update, context, "缓存已失效，请重新下载后再分享")
		return False

	targets = TEST_CHANNEL
	# targets = [x for x in (FURRY_READING, FURRY_NOVELS, FURRY_READING_NEW_GROUP) if x]
	if not targets:
		await reply(update, context, "未配置分享频道")
		return False

	query = update.callback_query
	caption = [cached.caption, ""]
	if public and query and query.from_user:
		caption.append(f"来自 {query.from_user.first_name} 的分享")
	else:
		caption.append("来自 匿名用户 的分享")
	caption.append(f"喜欢还请去Pixiv收藏或评论，以支持作者 {FURRY_READING}")
	caption = "\n".join(caption)
	title = (cached.caption or "").splitlines()[0] if cached.caption else ""

	_inflight.add(share_key)
	try:
		await upload_file(
			update, context, file_id=cached.file_id, filename=cached.file_name,
			chat_id=targets, caption=caption, cache_key=cache_key)
	except Exception:
		logger.exception("分享失败 %s", share_key)
		raise
	finally:
		_inflight.discard(share_key)

	user = query.from_user if query else None
	record = records.record(
		share_key,
		kind=kind,
		item_id=item_id,
		title=title,
		user_id=user.id if user else None,
		user_name=(user.first_name or "") if user else "",
		chat_ids=targets,
		file_type=file_type,
		public=public,
	)
	logger.info(f"分享记录 {share_key} {record.count}")
	return True


async def share_public(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	if await share(update, context, data=data, public=True):
		await reply(update, context, f"已经公开分享至 {FURRY_READING}")


async def share_private(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	if await share(update, context, data=data, public=False):
		await reply(update, context, f"已经匿名分享至 {FURRY_READING}")


async def share_reject(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		**kwargs) -> None:
	query = update.callback_query
	if query is not None:
		await query.edit_message_reply_markup(reply_markup=None)
