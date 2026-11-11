"""下架业务：作者被拉黑后，删掉频道里的历史分享并清理记录。

Telegram 相关部分留在 handlers：
  - 本模块不 import telegram；
  - 删除通过 `takedown(..., delete=...)` 注入，回调抛异常即视为该条失败。

三条规则：
  - 删成功 → 从记录里移除这条消息；
  - 删失败 → **保留**记录，下次重试还能拿到 (chat_id, message_id)；
  - 记录里没有句柄（`message_id = 0`，升级前的老数据）→ 删不掉，只清记录并计入
    `skipped`，由管理员手工处理。
全部不再失败时，整个作者节点一起删掉。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from services.share_service import get_share_records
from storage.share_records import ShareRecordStore


logger = logging.getLogger(__name__)

# 删除一条频道消息；失败直接抛异常（"消息已不存在"由 handler 吞掉）
TakedownDelete = Callable[[str, int], Awaitable[None]]


@dataclass(frozen=True)
class TakedownResult:
	"""一次下架的结果；handler 据此补充审核回执。"""

	author_id: str
	deleted: int = 0
	failed: int = 0
	skipped: int = 0
	errors: tuple[str, ...] = ()

	@property
	def total(self) -> int:
		return self.deleted + self.failed + self.skipped

	@property
	def ok(self) -> bool:
		return self.failed == 0


class TakedownService:
	"""下架用例的统一入口。"""

	def __init__(self, records: ShareRecordStore | None = None) -> None:
		self._records = records


	@property
	def records(self) -> ShareRecordStore:
		if self._records is None:
			self._records = get_share_records()
		return self._records


	async def takedown(
		self,
		author_id: str | int,
		*,
		delete: TakedownDelete,
	) -> TakedownResult:
		"""按作者删除全部历史分享，返回各状态计数。"""
		key = str(author_id or "").strip()
		if not key:
			return TakedownResult("")

		rows = self.records.by_author(key)
		deleted = skipped = 0
		errors: list[str] = []

		for row in rows:
			chat_id = str(row.chat_id or "")
			message_id = int(row.message_id or 0)
			if not chat_id or message_id <= 0:
				# 没有句柄：删不掉，只能清记录
				self.records.remove_message(
					key, row.kind, row.item_id, chat_id, message_id)
				skipped += 1
				continue
			try:
				await delete(chat_id, message_id)
			except Exception as exc:
				logger.warning(
					"下架失败 author=%s chat=%s message=%s",
					key, chat_id, message_id, exc_info=True)
				errors.append(f"{chat_id}/{message_id}: {exc}")
				continue
			self.records.remove_message(
				key, row.kind, row.item_id, chat_id, message_id)
			deleted += 1

		failed = len(errors)
		if failed == 0:
			self.records.drop_author(key)
		logger.info(
			"下架完成 author=%s deleted=%s skipped=%s failed=%s",
			key, deleted, skipped, failed)
		return TakedownResult(
			key,
			deleted=deleted,
			failed=failed,
			skipped=skipped,
			errors=tuple(errors),
		)
