"""文件发送：只负责把一个文件发到一个会话，缓存与记录由服务层决定。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes


@dataclass(frozen=True)
class SentDocument:
	"""一次 send_document 的结果：file_id 用于缓存复用，message_id 用于日后下架。"""

	file_id: str
	message_id: int


async def upload_file(
	update: Update,
	context: ContextTypes.DEFAULT_TYPE,
	*,
	path: str | Path | None = None,
	file_id: str | None = None,
	filename: str | None = None,
	chat_id: int | str | None = None,
	reply_markup: InlineKeyboardMarkup | None = None,
	caption: str | None = None,
	reply_to_message_id: int | None = None,
) -> SentDocument:
	"""优先用 file_id 发送，否则上传本地文件；失败直接抛出。

	chat_id 为空时发到当前会话。
	"""
	if chat_id is None:
		effective = update.effective_chat
		if effective is None:
			raise ValueError("无法确定发送目标，请显式传入 chat_id")
		chat_id = effective.id

	file_path = Path(path) if path else None
	if not file_id and (not file_path or not file_path.is_file()):
		raise FileNotFoundError(file_path or "(no path)")

	handle = None
	try:
		if file_id:
			document: object = file_id
			send_name = filename
		else:
			handle = file_path.open("rb")
			document = handle
			send_name = filename or file_path.name

		sent = await context.bot.send_document(
			chat_id=chat_id,
			document=document,
			filename=send_name,
			caption=(caption[:1024] if caption else None),
			reply_markup=reply_markup,
			reply_to_message_id=reply_to_message_id,
		)
	finally:
		if handle is not None:
			handle.close()

	new_id = sent.document.file_id if sent.document is not None else None
	return SentDocument(
		file_id=new_id or str(file_id or ""),
		message_id=int(sent.message_id),
	)
