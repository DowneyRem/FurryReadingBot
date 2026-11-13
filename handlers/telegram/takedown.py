"""频道消息删除适配：把下架服务要的 (chat_id, message_id) 换成 Telegram 调用。"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from telegram.error import BadRequest, RetryAfter

from services import TakedownResult, TakedownService


if TYPE_CHECKING:
	from telegram.ext import ContextTypes


logger = logging.getLogger(__name__)


def chat_target(chat_id: str | int) -> int | str:
	"""`-1001234567890` 转整数；`@channel` 这类用户名原样返回。"""
	text = str(chat_id or "").strip()
	if text.lstrip("-").isdigit():
		return int(text)
	return text


async def delete_message(
		context: ContextTypes.DEFAULT_TYPE,
		chat_id: str | int,
		message_id: int) -> None:
	"""删一条频道消息；「消息已不存在」视为成功，保证下架可重放；被限流时等待后重试一次。"""
	try:
		await _delete(context, chat_id, message_id)
	except RetryAfter as exc:
		wait = exc.retry_after
		await asyncio.sleep(wait.total_seconds() if hasattr(wait, "total_seconds") else wait)
		await _delete(context, chat_id, message_id)


async def _delete(
		context: ContextTypes.DEFAULT_TYPE,
		chat_id: str | int,
		message_id: int) -> None:
	try:
		await context.bot.delete_message(
			chat_id=chat_target(chat_id), message_id=message_id)
	except BadRequest as exc:
		if "not found" in str(exc).lower():
			return
		raise


async def takedown_author(
		context: ContextTypes.DEFAULT_TYPE,
		author_id: str | int) -> TakedownResult:
	"""按作者下架全部历史分享（拉黑时调用）。"""
	async def delete(chat_id: str, message_id: int) -> None:
		await delete_message(context, chat_id, message_id)

	return await TakedownService().takedown(author_id, delete=delete)
