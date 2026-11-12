"""审核业务：申请状态、作者名单更新、并发幂等与失败回滚。

Telegram 相关部分留在 handlers：
  - 本模块不 import telegram；
  - 审核回执、中转消息、私聊通知由 handler 负责。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from storage import ListManager, get_lists
from storage.furry_request import FurryRequestStore, get_furry_requests
from utils.json import JsonDict


logger = logging.getLogger(__name__)

ReviewDecision = Literal["approve", "reject"]
ReviewStatus = Literal[
	"approved", "rejected", "missing", "already_processed",
]


@dataclass(frozen=True)
class ReviewResult:
	"""一次审核的结果；handler 据此生成回执和通知。"""

	status: ReviewStatus
	author_id: str
	author_name: str = ""
	previous_status: str = ""
	record: JsonDict | None = None


class ReviewService:
	"""审核用例的统一入口。"""

	def __init__(
		self,
		furry_requests: FurryRequestStore | None = None,
		*,
		list_manager: ListManager | None = None,
	) -> None:
		self._furry_requests = furry_requests
		self._list_manager = list_manager


	@property
	def furry_requests(self) -> FurryRequestStore:
		if self._furry_requests is None:
			self._furry_requests = get_furry_requests()
		return self._furry_requests


	@property
	def list_manager(self) -> ListManager:
		if self._list_manager is None:
			self._list_manager = get_lists()
		return self._list_manager


	def review(
		self,
		author_id: str,
		decision: ReviewDecision,
		*,
		reviewer_id: str | int | None = None,
		reviewer_name: str = "",
	) -> ReviewResult:
		"""审核一条申请；同一申请只会成功处理一次。

		只裁决「通过 / 拒绝」。拉黑是作者本人的诉求，不走这里——
		管理员核验的是「这位用户替作者提的申请是否成立」。
		"""
		if decision not in ("approve", "reject"):
			raise ValueError(f"未知审核决定：{decision}")

		current = self.furry_requests.get(author_id)
		if current is None:
			return ReviewResult("missing", author_id)

		previous = str(current.status or "")
		name = str(current.author_name or author_id)
		if previous != FurryRequestStore.STATUS_PENDING:
			return ReviewResult(
				status="already_processed",
				author_id=author_id,
				author_name=name,
				previous_status=previous,
				record=current,
			)

		if decision == "approve":
			if not self.furry_requests.set_status(
				author_id, FurryRequestStore.STATUS_APPROVED,
				expected=FurryRequestStore.STATUS_PENDING,
			):
				return self._already_processed(author_id, current)

			try:
				self.list_manager.add_furrylist(
					author_id, name=name, note="兽人作者申请通过")
			except Exception:
				self._rollback(author_id, FurryRequestStore.STATUS_APPROVED)
				raise
			result = self._updated(
				author_id, "approved", previous, current)
		else:
			if not self.furry_requests.set_status(
				author_id, FurryRequestStore.STATUS_REJECTED,
				expected=FurryRequestStore.STATUS_PENDING,
			):
				return self._already_processed(author_id, current)

			result = self._updated(
				author_id, "rejected", previous, current)

		logger.info(
			"申请核验 author=%s decision=%s reviewer=%s(%s)",
			author_id, decision, reviewer_name, reviewer_id,
		)
		return result


	def _updated(
		self,
		author_id: str,
		status: Literal["approved", "rejected"],
		previous: str,
		fallback: JsonDict,
	) -> ReviewResult:
		record = self.furry_requests.get(author_id) or fallback
		return ReviewResult(
			status=status,
			author_id=author_id,
			author_name=str(record.author_name or author_id),
			previous_status=previous,
			record=record,
		)


	def _already_processed(
		self, author_id: str, fallback: JsonDict) -> ReviewResult:
		current = self.furry_requests.get(author_id) or fallback
		return ReviewResult(
			status="already_processed",
			author_id=author_id,
			author_name=str(current.author_name or author_id),
			previous_status=str(current.status or ""),
			record=current,
		)


	def _rollback(self, author_id: str, from_status: str) -> None:
		"""名单更新失败时，把申请状态退回 pending，便于重新审核。"""
		try:
			self.furry_requests.set_status(
				author_id, FurryRequestStore.STATUS_PENDING,
				expected=from_status)
		except Exception:
			logger.exception("申请 %s 状态回滚失败", author_id)
