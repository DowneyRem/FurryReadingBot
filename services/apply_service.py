"""申请业务：链接解析、名单校验、重复待审、写入申请记录、送审编排。

Telegram 相关部分留在 handlers：
  - 本模块不 import telegram；
  - 送中转通过 `submit(..., send_transit=...)` 注入；
  - handler 只负责文案、键盘和消息编辑。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from sources import fetch as sources_fetch
from policy.author import AuthorPolicy
from storage import ListManager, get_lists
from storage.applications import ApplicationStore
from utils.json import JsonDict
from utils.links import get_id


logger = logging.getLogger(__name__)

ApplyInspectionStatus = Literal[
	"needs_confirm", "pending", "blacklisted", "already_furry",
]
ApplySubmissionStatus = Literal[
	"submitted", "pending", "blacklisted", "already_furry",
]


class ApplyError(Exception):
	"""申请相关错误的基类。"""


class ApplyInvalidLinkError(ApplyError):
	"""链接里解析不出作者 ID。"""


@dataclass(frozen=True)
class ApplyInspection:
	"""申请前的检查结果，handler 据此渲染提示或确认按钮。"""

	status: ApplyInspectionStatus
	author_id: str
	author_name: str
	link: str
	record: JsonDict | None = None


@dataclass(frozen=True)
class ApplySubmission:
	"""提交结果；`transit_sent` 表示中转频道消息是否成功发出。"""

	status: ApplySubmissionStatus
	author_id: str
	author_name: str
	link: str
	record: JsonDict | None = None
	transit_sent: bool = False


TransitCallback = Callable[[JsonDict], Awaitable[bool]]


_applications: ApplicationStore | None = None


def get_applications() -> ApplicationStore:
	"""申请记录是进程级单例，申请与核验共用同一份数据。"""
	global _applications
	if _applications is None:
		_applications = ApplicationStore()
	return _applications


class ApplyService:
	"""申请用例的统一入口。"""

	def __init__(
		self,
		applications: ApplicationStore | None = None,
		*,
		list_manager: ListManager | None = None,
		policy: AuthorPolicy | None = None,
		fetch_fn: Callable[[str], Awaitable[object]] | None = None,
	) -> None:
		self._applications = applications
		self._list_manager = list_manager
		self._policy = policy
		self._fetch = fetch_fn or sources_fetch


	@property
	def applications(self) -> ApplicationStore:
		if self._applications is None:
			self._applications = get_applications()
		return self._applications


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


	def pending_records(self) -> list[JsonDict]:
		"""返回所有待审核申请，供 `/review` 重推使用。"""
		return [
			record for record in self.applications.records().values()
			if str(record.status or "") == ApplicationStore.STATUS_PENDING
		]


	async def inspect(self, link: str) -> ApplyInspection:
		"""检查作者是否可申请，并返回申请所需信息。"""
		author_id = self._author_id(link)
		blocked = self._blocked(link, author_id)
		if blocked is not None:
			return blocked

		record = self.applications.get(author_id)
		if record and str(record.status or "") == ApplicationStore.STATUS_PENDING:
			return ApplyInspection(
				status="pending",
				author_id=author_id,
				author_name=str(record.author_name or author_id),
				link=link,
				record=record,
			)

		author = await self._fetch(link)
		name = str(getattr(author, "author_name", "") or author_id)
		return ApplyInspection(
			status="needs_confirm",
			author_id=author_id,
			author_name=name,
			link=link,
		)


	async def submit(
		self,
		link: str,
		*,
		user_id: str | int,
		user_name: str,
		send_transit: TransitCallback | None = None,
	) -> ApplySubmission:
		"""检查 -> 写入申请记录 -> 送中转，返回提交结果。"""
		inspection = await self.inspect(link)
		if inspection.status != "needs_confirm":
			return ApplySubmission(
				status=inspection.status,
				author_id=inspection.author_id,
				author_name=inspection.author_name,
				link=link,
				record=inspection.record,
			)

		# inspect 与 submit 之间可能被其他用户抢先提交，再确认一次
		record = self.applications.get(inspection.author_id)
		if record and str(record.status or "") == ApplicationStore.STATUS_PENDING:
			return ApplySubmission(
				status="pending",
				author_id=inspection.author_id,
				author_name=str(record.author_name or inspection.author_id),
				link=link,
				record=record,
			)

		record = self.applications.submit(
			inspection.author_id,
			author_name=inspection.author_name,
			link=link,
			user_id=user_id,
			user_name=user_name,
		)
		logger.info(
			"收到兽人作者申请：%s=(%s) count=%s user=%s",
			record.author_name, record.author_id, record.count, record.user_id,
		)

		transit_sent = False
		if send_transit is not None:
			try:
				transit_sent = bool(await send_transit(record))
			except Exception:
				logger.exception("申请 %s 送中转失败", record.author_id)

		return ApplySubmission(
			status="submitted",
			author_id=inspection.author_id,
			author_name=str(record.author_name or inspection.author_name),
			link=link,
			record=record,
			transit_sent=transit_sent,
		)


	def _author_id(self, link: str) -> str:
		author_id = get_id(link)
		if not author_id:
			raise ApplyInvalidLinkError("无法从链接中解析作者 ID。")
		return author_id


	def _blocked(self, link: str, author_id: str) -> ApplyInspection | None:
		"""黑名单禁止申请；已在兽人作者名单则无需申请。"""
		decision = self.policy.check(author_id)
		if decision.status == "blacklisted":
			return ApplyInspection(
				"blacklisted", decision.author_id, decision.author_name, link)
		if decision.status == "furry":
			return ApplyInspection(
				"already_furry", decision.author_id, decision.author_name, link)
		return None
