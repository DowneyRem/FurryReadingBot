"""作者拉黑申请业务：材料收集、状态流转与名单更新。

两条互斥规则（都用 `user_id` 判定，不需要额外状态字段）：

- **同一作者同一时间只允许一个用户受理**：别人正在交截图（`pending_material`）
  或在等核验（`pending_review`）时，第二位用户拿到 `other_applicant`。
  以前这里会被覆盖，导致前一位用户发来的截图被静默丢弃。
- **同一用户同时只保留一条「等截图」**：已有别的作者的材料没交时，
  新受理返回 `material_open`，避免 `pending_material_for_user()` 认错作者。

同一作者 1 天内只能申请一次（`config.APPLY_COOLDOWN_HOURS`，见
`storage.black_request.BlackRequestStore.apply_remaining`）；
冷却按「提交截图送审」算，只点受理不交截图不会占冷却（那条受理 30 分钟后作废）。

Telegram 相关部分留在 handlers：
  - 本模块不 import telegram；
  - 送审卡片、删卡片、私聊通知都由 handler 做；
  - 核验通过只更新名单（黑名单 + 移出兽人名单）；频道里的历史分享由 handler
    在通过后调 `handlers.telegram.takedown · takedown_author` 下架
    （`services/takedown_service.py`），本模块不碰删除。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from policy.author import AuthorPolicy
from storage import ListManager, get_lists
from storage.black_request import (
	BlackRequestStore,
	get_black_requests,
)
from utils.json import JsonDict


logger = logging.getLogger(__name__)

RequestStatus = Literal[
	"needs_material", "pending_review", "cooldown",
	"other_applicant", "material_open", "already_blacklisted",
]
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
	# status == "cooldown" 时还要等多少秒（同一作者 1 天只能申请一次）
	# status == "material_open" 时是该用户另一条「等截图」还剩多少秒
	remaining_seconds: float = 0.0
	# status == "material_open" 时指向那条还没交截图的申请（别的作者）
	pending_record: JsonDict | None = None


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
		black_requests: BlackRequestStore | None = None,
		*,
		list_manager: ListManager | None = None,
		policy: AuthorPolicy | None = None,
	) -> None:
		self._black_requests = black_requests
		self._list_manager = list_manager
		self._policy = policy


	@property
	def black_requests(self) -> BlackRequestStore:
		if self._black_requests is None:
			self._black_requests = get_black_requests()
		return self._black_requests


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
		"""受理一次「申请下架」：回材料清单，或说明这次受理为什么不成立。"""
		key = str(author_id or "").strip()
		if not key:
			raise ValueError("作者 ID 为空")

		decision = self.policy.check(key)
		if decision.status == "blacklisted":
			return BlacklistRequest("already_blacklisted", key, decision.author_name)

		existing = self.black_requests.get(key)
		# 「等截图」窗口过期就作废：否则一条没人交图的受理会把作者永久占住
		if (existing is not None
				and existing.status == BlackRequestStore.STATUS_MATERIAL
				and self.black_requests.is_stale(existing)):
			self.black_requests.discard_material(key)
			existing = None

		current = str(user_id or "")
		holder = str((existing.user_id if existing else "") or "")
		# 只有「进行中」的受理才锁人：已拒绝 / 已通过的旧记录不能挡住别人，
		# 否则一条 rejected 记录会让这个作者对其他人永久不可申请
		in_progress = existing is not None and existing.status in (
			BlackRequestStore.STATUS_MATERIAL,
			BlackRequestStore.STATUS_REVIEW,
		)
		if in_progress and holder and current and holder != current:
			# 同一作者同一时间只允许一个用户受理：别人正在交截图 / 等核验
			return BlacklistRequest(
				status="other_applicant",
				author_id=key,
				author_name=str(existing.author_name or decision.author_name),
				record=existing,
			)

		if existing is not None and existing.status == BlackRequestStore.STATUS_REVIEW:
			name = str(existing.author_name or decision.author_name)
			return BlacklistRequest("pending_review", key, name, existing)

		remaining = self.black_requests.apply_remaining(key)
		if remaining > 0:
			name = str(
				(existing.author_name if existing else "") or decision.author_name)
			return BlacklistRequest("cooldown", key, name, existing, remaining)

		# 同一用户同时只留一条待交材料：先把上一张截图交了
		pending = self.black_requests.other_material_for_user(user_id, key)
		if pending is not None and self.black_requests.is_stale(pending):
			self.black_requests.discard_material(pending.author_id)
			pending = None
		if pending is not None:
			return BlacklistRequest(
				status="material_open",
				author_id=key,
				author_name=str(author_name or decision.author_name),
				remaining_seconds=self.black_requests.material_remaining(pending),
				pending_record=pending,
			)

		record = self.black_requests.open(
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
		record = self.black_requests.pending_material_for_user(user_id)
		if record is None:
			return MaterialSubmission("no_request")
		if self.black_requests.is_stale(record):
			# 只提示一次：过期申请随即作废，之后的图片按普通图片忽略
			self.black_requests.discard_material(record.author_id)
			return MaterialSubmission("expired", record)
		if not self.black_requests.attach_photo(record.author_id, photo_file_id):
			return MaterialSubmission("no_request", record)
		logger.info(
			"作者下架材料已提交 author=%s user=%s",
			record.author_id, user_id)
		return MaterialSubmission("submitted", self.black_requests.get(record.author_id))


	def pending_review_records(self) -> list[JsonDict]:
		"""已交截图、等管理员核验的申请，供 `/review` 重推卡片。"""
		return [
			record for record in self.black_requests.records().values()
			if record.status == BlackRequestStore.STATUS_REVIEW
		]


	def can_retry_takedown(self, author_id: str | int) -> bool:
		"""「重试删除」只对仍在黑名单的作者生效，避免旧回执误删已解除拉黑的作者。"""
		return self.policy.check(str(author_id)).is_blacklisted


	def review(self, author_id: str | int, decision: BlacklistDecision) -> BlacklistReview:
		"""管理员核验：通过 = 进黑名单 + 移出兽人名单；拒绝 = 只改状态。"""
		if decision not in ("approve", "reject"):
			raise ValueError(f"未知核验决定：{decision}")

		key = str(author_id or "").strip()
		record = self.black_requests.get(key) if key else None
		if record is None:
			return BlacklistReview("missing", key)

		name = str(record.author_name or key)
		status = BlackRequestStore.STATUS_REVIEW
		if record.status != status:
			return BlacklistReview("already_processed", key, name, record)

		if decision == "reject":
			if not self.black_requests.set_status(
				key, BlackRequestStore.STATUS_REJECTED, expected=status):
				return self._already_processed(key, record)
			logger.info("作者下架申请被拒绝 author=%s", key)
			return BlacklistReview(
				"rejected", key, name, self.black_requests.get(key) or record)

		if not self.black_requests.set_status(
			key, BlackRequestStore.STATUS_APPROVED, expected=status):
			return self._already_processed(key, record)

		try:
			self.list_manager.add_blacklist(
				key, name=name, note="作者本人申请下架")
			self.list_manager.remove_furrylist(key)
		except Exception:
			# 名单写失败：把申请退回待核验，便于重试
			self.black_requests.set_status(
				key, BlackRequestStore.STATUS_REVIEW,
				expected=BlackRequestStore.STATUS_APPROVED)
			raise

		logger.info("作者下架申请已通过 author=%s", key)
		return BlacklistReview(
			"approved", key, name, self.black_requests.get(key) or record)


	def _already_processed(self, key: str, fallback: JsonDict) -> BlacklistReview:
		current = self.black_requests.get(key) or fallback
		return BlacklistReview(
			"already_processed",
			key,
			str(current.author_name or key),
			current,
		)
