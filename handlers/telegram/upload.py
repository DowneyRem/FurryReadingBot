"""文件上传 + file_id 缓存写入。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from infra.files import remove_file
from storage.file_cache import FileCacheStore, get_file_cache


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SentDocument:
	"""一次 send_document 的结果：file_id 用于缓存复用，message_id 用于日后下架。"""

	file_id: str
	message_id: int


def get_cache() -> FileCacheStore:
	"""兼容旧调用方：返回共享的 file_id 缓存。"""
	return get_file_cache()


async def upload_file(
	update: Update,
	context: ContextTypes.DEFAULT_TYPE,
	*,
	path: str | Path | None = None,
	file_id: str | None = None,
	filename: str | None = None,
	chat_id: int | str | Iterable[int | str] | None = None,
	reply_markup: InlineKeyboardMarkup | None = None,
	caption: str | None = None,
	reply_to_message_id: int | None = None,
	cache_key: str | None = None,
	cleanup: bool = False,
	author_id: str | int = "",
	author_name: str = "",
) -> dict[int | str, SentDocument]:
	"""优先 file_id；否则上传 path，成功后写入 FileCacheStore。

	返回值按目标频道给出 file_id + message_id（下架要用 message_id）。
	"""
	
	file_path = Path(path) if path else None
	store = get_cache()

	if not file_id and cache_key:
		cached = store.get_valid(cache_key)
		if cached:
			file_id = cached.file_id
			filename = filename or cached.file_name or None

	if chat_id is None:
		effective = update.effective_chat
		if effective is None:
			raise ValueError("无法确定发送目标，请显式传入 chat_id")
		targets: list[int | str] = [effective.id]
	elif isinstance(chat_id, (str, int)):
		targets = [chat_id]
	else:
		targets = list(dict.fromkeys(chat_id))

	if not targets:
		raise ValueError("至少需要一个发送目标")

	if not file_id and (not file_path or not file_path.is_file()):
		raise FileNotFoundError(file_path or "(no path)")

	documents: dict[int | str, SentDocument] = {}
	last_file_id: str | None = None
	used_local_upload = False

	for target in targets:
		handle = None
		try:
			if file_id:
				document: object = file_id
				send_name = filename
			else:
				handle = file_path.open("rb")
				document = handle
				send_name = filename or file_path.name
				used_local_upload = True

			sent = await context.bot.send_document(
				chat_id=target,
				document=document,
				filename=send_name,
				caption=(caption[:1024] if caption else None),
				reply_markup=reply_markup,
				reply_to_message_id=(reply_to_message_id if len(targets) == 1 else None),
			)
		finally:
			if handle is not None:
				handle.close()

		new_id = None
		if sent.document is not None:
			new_id = sent.document.file_id
		elif getattr(sent, "video", None) is not None:
			new_id = sent.video.file_id

		if new_id:
			last_file_id = new_id

		documents[target] = SentDocument(
			file_id=new_id or str(file_id or ""),
			message_id=int(getattr(sent, "message_id", 0) or 0),
		)

	if used_local_upload and last_file_id and cache_key:
		store.set(
			cache_key,
			last_file_id,
			file_name=filename or (file_path.name if file_path else ""),
			caption=caption or "",
			author_id=author_id,
			author_name=author_name,
		)

	if cleanup and file_path and file_path.is_file():
		await remove_file(file_path)

	return documents
