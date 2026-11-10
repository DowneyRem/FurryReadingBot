"""下载类 callback：dn / ds / dst / dsz / dan。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from keyboards import down_series_keyboard, share_novel_keyboard
from sources import fetch, save, resolve_link
from storage.file_async import remove_file
from storage.file_cache import FileCacheStore
from utils.json import JsonDict
from utils.links import get_id

from handlers.callbacks.common import reply
from handlers.callbacks.upload import get_cache, upload_file


logger = logging.getLogger(__name__)


async def choose_series_format(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, link: str) -> None:
	"""series 的 txt 与 zip 缓存同时存在时，编辑当前按钮让用户做选择。"""
	text = "该系列已有 txt 与 zip 缓存，请选择要下载的格式"
	markup = down_series_keyboard(link, auto=False)
	query = update.callback_query
	if query:
		await query.edit_message_text(text, reply_markup=markup)
	else:
		await reply(update, context, text, reply_markup=markup, delete_after=0)


def find_cached(
		store: FileCacheStore, kind: str, item_id: str, file_type: str
		) -> list[tuple[str, str, JsonDict]]:
	"""查找有效缓存，返回 [(file_type, cache_key, cached), ...]。"""
	# auto 时依次尝试复用的缓存格式
	
	AUTO_CANDIDATES = ("txt", "zip")
	types = AUTO_CANDIDATES if file_type == "auto" else (file_type,)
	hits: list[tuple[str, str, JsonDict]] = []
	for candidate in types:
		cache_key = FileCacheStore.make_key(kind, item_id, candidate)
		cached = store.get_valid(cache_key)
		if cached:
			hits.append((candidate, cache_key, cached))
	return hits


async def download(
	update: Update, context: ContextTypes.DEFAULT_TYPE,
	*, data: str,) -> None:
	
	query = update.callback_query
	action, _, link = data.partition(";")
	
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
	if query:
		await query.edit_message_text("正在获取文件，请稍候……")

	# 解析真正要下载的目标：单篇链接要求下载系列时，会解析为其所属系列
	target_link = await resolve_link(link, kind)
	item_id = get_id(target_link)
	logger.debug(" ".join([action, kind, item_id, file_type, target_link]))
	
	# 获取缓存
	store = get_cache()
	cache_key = FileCacheStore.make_key(kind, item_id, file_type)
	cached: JsonDict | None = None

	# series auto：优先复用已有的 txt / zip 缓存；
	# 两种都在时，编辑当前按钮让用户其选择
	if file_type == "auto" and kind == "series":
		hits = find_cached(store, kind, item_id, file_type)
		if len(hits) > 1:
			await choose_series_format(update, context, link=target_link)
			return
		if hits:
			file_type, cache_key, cached = hits[0]
			logger.info(f"自动命中缓存 {cache_key} {cached.file_name}")
	else:
		cached = store.get_valid(cache_key)

	path: Path | None = None
	file_id: str | None = None
	filename: str | None = None
	if cached:
		file_id = cached.file_id
		filename = cached.file_name
		caption = cached.caption
		logger.info(f"命中缓存 {cache_key} {filename}")
		
	else:
		item = await fetch(target_link)
		caption = f"{str(item)}\n{item.url}"
		
		path = Path(await save(target_link, file_type))
		if file_type == "auto":
			file_type = path.suffix.lstrip(".").lower() or "txt"
			cache_key = FileCacheStore.make_key(kind, item_id, file_type)
			cached = store.get_valid(cache_key)
			if cached:
				file_id = cached.file_id
				filename = cached.file_name or path.name
				if path.is_file():
					await remove_file(path)
				path = None

	await upload_file(
		update, context, path=path, file_id=file_id, filename=filename,
		reply_markup=share_novel_keyboard(kind, item_id, file_type),
		caption=caption, cache_key=cache_key, cleanup=True)

	if query:
		await query.edit_message_text("还请去源网站，给作者一个收藏/评论，以表支持")
		try:
			await asyncio.sleep(2)
			await query.delete_message()
		except Exception:
			pass

