"""作者拉黑申请业务：材料收集、状态流转与名单更新。

Telegram 相关部分留在 handlers：
  - 本模块不 import telegram；
  - 送审卡片、删卡片、私聊通知都由 handler 做；
  - 核验通过只更新名单（黑名单 + 移出兽人名单），**不删除历史分享**：
    下架能力已经写好（`services/takedown_service.py`），按产品决定暂不接入。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from policy.author import AuthorPolicy
from storage import ListManager, get_lists
from storage.black_request import (
	BlacklistRequestStore,
	get_blacklist_requests,
)
from utils.json import JsonDict


logger = logging.getLogger(__name__)

RequestStatus = Literal["needs_material", "pending_review", "already_blacklisted"]
SubmitStatus = Literal["submitted", "no_request", "expired"]
ReviewStatus = Literal["approved", "rejected", "missing", "already_processed"]
BlacklistDecision = Literal["approve", "reject"]


@dataclass(frozen=True)
class BlacklistRequest:
	"""一次「申请下架」的受理结果，handler 据此决定回复哪段文案。"""

	status: RequestStatus
	author_id: str
	author_name: str = ""
	record: JsonDict | None = None


@dataclass(frozen=True)
class MaterialSubmission:
	"""截图提交结果。"""

	status: SubmitStatus
	record: JsonDict | None = None


@dataclass(frozen=True)
class BlacklistReview:
	"""一次核验的结果。"""

	status: ReviewStatus
	author_id: str
	author_name: str = ""
	record: JsonDict | None = None


class BlacklistService:
	"""作者下架申请的统一入口。"""

	def __init__(
		self,
		requests: BlacklistRequestStore | None = None,
		*,
		list_manager: ListManager | None = None,
		policy: AuthorPolicy | None = None,
	) -> None:
		self._requests = requests
		self._list_manager = list_manager
		self._policy = policy


	@property
	def requests(self) -> BlacklistRequestStore:
		if self._requests is None:
			self._requests = get_blacklist_requests()
		return self._requests


	@property
	def list_manager(self) -> ListManager:
		if self._list_manager is None:
			self._list_manager = get_lists()
		return self._list_manager


	@property
	def policy(self) -> AuthorPolicy:
		if self._policy is None:
			self._policy = AuthorPolicy(self.list_manager)
		return self._policy


	def request(
		self,
		author_id: str | int,
		*,
		author_url: str = "",
		author_name: str = "",
		user_id: str | int | None = None,
		user_name: str = "",
	) -> BlacklistRequest:
		"""受理一次「申请下架」：回材料清单、提示已在核验，或已在黑名单。"""
		key = str(author_id or "").strip()
		if not key:
			raise ValueError("作者 ID 为空")

		decision = self.policy.check(key)
		if decision.status == "blacklisted":
			return BlacklistRequest("already_blacklisted", key, decision.author_name)

		existing = self.requests.get(key)
		if existing is not None and existing.status == self.requests.STATUS_REVIEW:
			name = str(existing.author_name or decision.author_name)
			return BlacklistRequest("pending_review", key, name, existing)

		record = self.requests.open(
			key,
			author_name=author_name or decision.author_name,
			author_url=author_url,
			user_id=user_id,
			user_name=user_name,
		)
		logger.info("收到作者下架申请 author=%s user=%s", key, user_id)
		return BlacklistRequest(
			"needs_material", key, str(record.author_name or ""), record)


	def submit_material(
		self,
		user_id: str | int | None,
		photo_file_id: str,
	) -> MaterialSubmission:
		"""把用户发来的截图挂到他的「等截图」申请上。"""
		record = self.requests.pending_material_for_user(user_id)
		if record is None:
			return MaterialSubmission("no_request")
		if self.requests.is_stale(record):
			return MaterialSubmission("expired", record)
		if not self.requests.attach_photo(record.author_id, photo_file_id):
			return MaterialSubmission("no_request", record)
		logger.info(
			"作者下架材料已提交 author=%s user=%s",
			record.author_id, user_id)
		return MaterialSubmission("submitted", self.requests.get(record.author_id))


	def review(self, author_id: str | int, decision: BlacklistDecision) -> BlacklistReview:
		"""管理员核验：通过 = 进黑名单 + 移出兽人名单；拒绝 = 只改状态。"""
		if decision not in ("approve", "reject"):
			raise ValueError(f"未知核验决定：{decision}")

		key = str(author_id or "").strip()
		record = self.requests.get(key) if key else None
		if record is None:
			return BlacklistReview("missing", key)

		name = str(record.author_name or key)
		status = self.requests.STATUS_REVIEW
		if record.status != status:
			return BlacklistReview("already_processed", key, name, record)

		if decision == "reject":
			if not self.requests.set_status(
				key, self.requests.STATUS_REJECTED, expected=status):
				return self._already_processed(key, record)
			logger.info("作者下架申请被拒绝 author=%s", key)
			return BlacklistReview(
				"rejected", key, name, self.requests.get(key) or record)

		if not self.requests.set_status(
			key, self.requests.STATUS_APPROVED, expected=status):
			return self._already_processed(key, record)

		try:
			self.list_manager.add_blacklist(
				key, name=name, note="作者本人申请下架")
			self.list_manager.remove_furrylist(key)
		except Exception:
			# 名单写失败：把申请退回待核验，便于重试
			self.requests.set_status(
				key, self.requests.STATUS_REVIEW,
				expected=self.requests.STATUS_APPROVED)
			raise

		logger.info("作者下架申请已通过 author=%s", key)
		return BlacklistReview(
			"approved", key, name, self.requests.get(key) or record)


	def _already_processed(self, key: str, fallback: JsonDict) -> BlacklistReview:
		current = self.requests.get(key) or fallback
		return BlacklistReview(
			"already_processed",
			key,
			str(current.author_name or key),
			current,
		)
