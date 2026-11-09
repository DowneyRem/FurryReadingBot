"""下载类 callback：dn / ds / dst / dsz / dan。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from keyboards import share_novel_keyboard
from sources import fetch, save
from sources.linpx.config import AUTHOR_PATTERN, NOVEL_PATTERN, SERIES_PATTERN
from sources.utils import get_id
from storage.file import remove_file
from storage.file_cache import FileCacheStore

from handlers.callbacks._common import reply
from handlers.callbacks.upload import get_cache, upload_file

logger = logging.getLogger(__name__)


async def download(
	update: Update,
	context: ContextTypes.DEFAULT_TYPE,
	*,
	action: str,
	rest: str,
	data: str,
) -> None:
	query = update.callback_query
	link = rest

	mapping = {
		"dn": ("novel", "txt"),
		"ds": ("series", "auto"),
		"dst": ("series", "txt"),
		"dsz": ("series", "zip"),
		"dan": ("author", "zip"),
	}
	if action not in mapping:
		await reply(update, context, "暂不支持该下载操作。")
		return

	kind, file_type = mapping[action]
	item_id = _extract_id(link, kind) or link.strip()
	cache_key = FileCacheStore.make_key(
		kind, item_id, file_type if file_type != "auto" else "auto"
	)

	if query:
		await query.edit_message_text("正在获取文件，请稍候……")

	store = get_cache()
	cached = store.get_valid(cache_key) if file_type != "auto" else None

	path: Path | None = None
	file_id: str | None = None
	filename: str | None = None

	if cached:
		file_id = cached.file_id
		filename = cached.filename or None
		logger.info("命中缓存 key=%s", cache_key)
	else:
		ext = "" if file_type == "auto" else file_type
		path = await save(link, ext) if ext else await save(link)
		path = Path(path)
		filename = path.name
		if file_type == "auto":
			real_type = path.suffix.lstrip(".").lower() or "txt"
			cache_key = FileCacheStore.make_key(kind, item_id, real_type)
			file_type = real_type
			cached = store.get_valid(cache_key)
			if cached:
				file_id = cached.file_id
				filename = cached.filename or filename
				if path.is_file():
					remove_file(path)
				path = None

	item = await fetch(link)
	novel_url = getattr(item, "novel_url", None) or link
	caption = f"{str(item)}\n{novel_url}"
	resolved_type = (
		file_type
		if file_type != "auto"
		else (path.suffix.lstrip(".") if path else "txt")
	)

	await upload_file(
		update,
		context,
		path=path,
		file_id=file_id,
		filename=filename,
		cache_key=cache_key,
		file_type=resolved_type,
		reply_markup=share_novel_keyboard(novel_url),
		caption=caption,
		cleanup=True,
	)

	if query:
		await query.edit_message_text("还请去源网站，给作者一个收藏/评论，以表支持")
		await asyncio.sleep(8)
		try:
			await query.delete_message()
		except Exception:
			pass


def _extract_id(link: str, kind: str) -> str | None:
	if str(link).isdigit():
		return str(link)
	pattern = {
		"novel": NOVEL_PATTERN,
		"series": SERIES_PATTERN,
		"author": AUTHOR_PATTERN,
	}.get(kind)
	if pattern is None:
		return None
	return get_id(link, pattern)
