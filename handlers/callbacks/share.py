"""分享类 callback：snp / sna / snn。"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks._common import reply
from handlers.callbacks.upload import upload_file, get_cache
from storage.file_cache import FileCacheStore
from config import FURRY_READING, FURRY_NOVELS, FURRY_READING_NEW_GROUP, TEST_CHANNEL


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

	await upload_file(
		update, context, file_id=cached.file_id, filename=cached.filename,
		chat_id=targets, caption=caption, cache_key=cache_key)
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
