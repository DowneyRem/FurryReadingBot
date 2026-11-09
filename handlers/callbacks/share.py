"""分享类 callback：snp / sna / snn。"""

from __future__ import annotations

import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks._common import reply
from handlers.callbacks.upload import upload_file, get_cache
from storage.file_cache import FileCacheStore
from config import FURRY_READING, FURRY_NOVELS, FURRY_READING_NEW_GROUP, TEST_CHANNEL


async def share(
	update: Update, context: ContextTypes.DEFAULT_TYPE,
	*, data: str, public: bool=True):
	
	parts = data.split(";")
	print(parts)
	if len(parts) < 2:
		await reply(update, context, "分享参数不完整")
		return

	kind, item_id = parts[1], parts[2]
	file_type = parts[3] if len(parts) > 2 else "txt"
	cache_key = FileCacheStore.make_key(kind, item_id, file_type)

	cached = get_cache().get_valid(cache_key)
	if not cached:
		await reply(update, context, "缓存已失效，请重新下载后再分享")
		return

	targets = TEST_CHANNEL
	# targets = [x for x in (TEST_CHANNEL) if x]
	if not targets:
		await reply(update, context, "未配置分享频道")
		return
	
	caption = [cached.caption, ""]
	if public:
		caption.append(f"来自 {update.callback_query.from_user.first_name} 的分享")
	else:
		caption.append(f"来自 匿名用户 的分享")
	caption.append(f"喜欢还请去Pixiv收藏或评论，以支持作者 {FURRY_READING}")
	caption = "\n".join(caption)
	await upload_file(
		update, context, file_id=cached.file_id, filename=cached.filename or None,
		chat_id=targets, caption=caption, cache_key=cache_key)


async def share_public(
	update: Update, context: ContextTypes.DEFAULT_TYPE,
	*, action: str, rest: str, data: str) -> None:
	await share(update, context, public=False, data=data)
	await reply(update, context, f"已经公开分享至 {FURRY_READING}")
	await asyncio.sleep(5)
	await context.bot.delete_message(
		chat_id=update.callback_query.message.chat.id,
		message_id=update.callback_query.message.message_id +1)


async def share_private(
	update: Update, context: ContextTypes.DEFAULT_TYPE,
	*, action: str, rest: str, data: str) -> None:
	await share(update, context, public=False, data=data)
	await reply(update, context, f"已经匿名分享至 {FURRY_READING}")
	await asyncio.sleep(5)
	await context.bot.delete_message(
		chat_id=update.callback_query.message.chat.id,
		message_id=update.callback_query.message.message_id +1)


async def share_reject(
	update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs) -> None:
	await update.callback_query.edit_message_reply_markup(reply_markup=None)
