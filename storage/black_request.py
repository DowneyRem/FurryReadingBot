"""作者拉黑申请：作者本人提交后台截图，管理员核验后加入黑名单。

	作者主页链接 → 点「申请下架」→ 提交截图 → 中转频道核验 → 拉黑

状态流转：

	pending_material（等截图） → pending_review（等管理员） → approved / rejected

key 为 author_id：一个作者一条记录，重复申请只累计 ``count``。
「等截图」有时限（``config.BLACK_REQUEST_MATERIAL_TTL_MINUTES``），过期后要重新点申请。
同一作者 1 天内只能申请一次（``config.APPLY_COOLDOWN_HOURS``）：冷却按
``last_apply_at``（提交截图送审的时间）算，只受理不交截图不受影响。

互斥规则（由 ``services.blacklist_service`` 执行，Store 只提供查询）：

- 一个作者同一时间只允许一个 ``user_id`` 受理：别人正在交截图 / 等核验时，
  第二位用户会被挡下（否则截图会挂到别人的名字下，或被静默丢弃）；
- 一个用户同一时间只保留一条「等截图」（``other_material_for_user``），
  这样 ``pending_material_for_user`` 反查作者时不会歧义。

「等截图」窗口过期后，下一个受理会**接手**同一条记录（``open()``）：
``created_at`` / ``count`` 保留，上一位申请人记进 ``previous_user_id``；
他再补发截图时由 ``taken_over_material_for_user`` 识别，提示重新申请。

已结束（通过 / 拒绝）的记录按 ``config.BLACK_REQUEST_TTL_DAYS`` 保留，到期在
``_prune()`` 里整条删掉。**仍在流程里的记录不按 TTL 淘汰**：``pending_material``
的窗口由 ``material_ttl_minutes`` 管，且过期后要被下一位申请人接手——删掉会丢掉
``count`` / ``previous_user_id``，让原申请人再发截图时收不到提示；``pending_review``
在等管理员核验，更不能自动消失。黑名单本身在 ``black_authors.json``，不受影响。
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from storage.json_store import config_default
from storage.request_store import AuthorRequestStore
from utils.json import JsonDict, to_int
from utils.time import parse_iso, remaining_seconds, utc_now_iso


class BlackRequestStore(AuthorRequestStore):
	"""作者下架申请记录，key 为 author_id。"""

	DATA_KEY = "black_request"
	RECORD_TTL_CONFIG = "BLACK_REQUEST_TTL_DAYS"

	STATUS_MATERIAL = "pending_material"
	STATUS_REVIEW = "pending_review"
	# STATUS_APPROVED / STATUS_REJECTED / CLOSED_STATUSES 继承自 AuthorRequestStore
	DEFAULT_STATUS = STATUS_MATERIAL

	def __init__(
		self,
		path: Path | None = None,
		*,
		material_ttl_minutes: float | None = None,
		apply_cooldown_hours: float | None = None,
		record_ttl_days: float | None = None,
	) -> None:
		if path is None:
			path = (
				Path(__file__).parent.parent.resolve()
				/ "data" / "black_request.json"
			)
		# 默认值只在 config 里定义；0 也是合法值（立即过期 / 不冷却），不能用 or 兜底
		self.material_ttl_minutes = config_default(
			material_ttl_minutes, "BLACK_REQUEST_MATERIAL_TTL_MINUTES")
		super().__init__(
			path,
			apply_cooldown_hours=apply_cooldown_hours,
			record_ttl_days=record_ttl_days,
		)

	def _normalize(self, info: Any) -> JsonDict | None:
		if not isinstance(info, dict):
			return None
		return JsonDict(
			author_id=str(info.get("author_id") or ""),
			author_name=str(info.get("author_name") or ""),
			author_url=str(info.get("author_url") or ""),
			user_id=str(info.get("user_id") or ""),
			user_name=str(info.get("user_name") or ""),
			status=str(info.get("status") or self.STATUS_MATERIAL),
			photo_file_id=str(info.get("photo_file_id") or ""),
			created_at=str(info.get("created_at") or ""),
			last_apply_at=str(info.get("last_apply_at") or ""),
			updated_at=str(info.get("updated_at") or ""),
			count=to_int(info.get("count")),
			note=str(info.get("note") or ""),
			# 上一位受理人：受理窗口过期后被新申请接手时记下，
			# 让原申请人再发截图时能收到「请重新申请」而不是静默
			previous_user_id=str(info.get("previous_user_id") or ""),
			previous_user_name=str(info.get("previous_user_name") or ""),
		)

	def open(
		self,
		author_id: str | int,
		*,
		author_name: str = "",
		author_url: str = "",
		user_id: str | int | None = None,
		user_name: str = "",
	) -> JsonDict:
		"""开始 / 重新开始一次申请：回到「等截图」，清掉上一张图。

		只是「受理」，还不算一次申请：``last_apply_at``（1 天冷却的起点）
		要等截图送审时才刷新，否则没交截图被作废后还要白等一天。

		如果上一条是**别人的**过期受理（窗口过时没人交图），这里会接手它：
		``created_at`` / ``count`` 保留，上一位申请人记进 ``previous_user_id``，
		这样他之后发来的截图能被识别成「你的受理已被接替」，给出重新申请的提示。
		"""
		now = utc_now_iso()
		with self._lock:
			self._maybe_reload()
			key = self.make_key(author_id)
			prev = self._items.get(key) or JsonDict()
			prev_user = str(prev.user_id or "")
			new_user = str(user_id or "") or prev_user
			takeover = bool(
				prev_user
				and prev_user != new_user
				and prev.status == self.STATUS_MATERIAL
			)
			self._items[key] = JsonDict(
				author_id=key,
				author_name=str(author_name or prev.author_name or ""),
				author_url=str(author_url or prev.author_url or ""),
				user_id=new_user,
				user_name=str(user_name or prev.user_name or ""),
				status=self.STATUS_MATERIAL,
				photo_file_id="",
				created_at=str(prev.created_at or now),
				last_apply_at=str(prev.last_apply_at or ""),
				updated_at=now,
				count=to_int(prev.count) + 1,
				note="",
				previous_user_id=prev_user if takeover else "",
				previous_user_name=str(prev.user_name or "") if takeover else "",
			)
			self._persist()
			return JsonDict(self._items[key])

	def attach_photo(self, author_id: str | int, photo_file_id: str) -> bool:
		"""把截图挂到「等截图」的申请上；状态不对返回 False。"""
		with self._lock:
			self._maybe_reload()
			key = self.make_key(author_id)
			record = self._items.get(key)
			if not record or record.status != self.STATUS_MATERIAL:
				return False
			now = utc_now_iso()
			self._items[key] = JsonDict({
				**record,
				"photo_file_id": str(photo_file_id or ""),
				"status": self.STATUS_REVIEW,
				# 送审才算一次申请：1 天冷却从这里起算
				"last_apply_at": now,
				"updated_at": now,
			})
			self._persist()
			return True

	def discard_material(self, author_id: str | int) -> None:
		"""作废一条仍在「等截图」的申请（截图超时后调用）。"""
		with self._lock:
			self._maybe_reload()
			key = self.make_key(author_id)
			record = self._items.get(key)
			if record and record.status == self.STATUS_MATERIAL:
				del self._items[key]
				self._persist()

	def pending_material_for_user(self, user_id: str | int | None) -> JsonDict | None:
		"""该用户最近一条「等截图」的申请（不判断是否过期）。

		由 ``request()`` 保证同一用户同时只有一条，所以结果唯一；
		若历史数据里有多条，取 ``updated_at`` 最新的那条。
		"""
		return self._latest_material(user_id)

	def other_material_for_user(
		self, user_id: str | int | None, author_id: str | int,
	) -> JsonDict | None:
		"""该用户在**其他作者**上是否还有「等截图」的申请（不判断是否过期）。

		「一个用户同时只留一条待交材料」由服务层执行，这里只负责查。
		"""
		return self._latest_material(user_id, exclude_author=author_id)

	def _latest_material(
		self,
		user_id: str | int | None,
		*,
		exclude_author: str | int | None = None,
	) -> JsonDict | None:
		"""该用户最近一条「等截图」记录；``exclude_author`` 排除指定作者。

		两个对外查询只差「要不要排掉当前作者」，扫描逻辑只写这一处。
		"""
		key = str(user_id or "")
		if not key:
			return None
		target = (
			self.make_key(exclude_author) if exclude_author is not None else None
		)
		self._maybe_reload()
		with self._lock:
			hits = [
				info for info in self._items.values()
				if str(info.user_id or "") == key
				and info.status == self.STATUS_MATERIAL
				and (target is None or self.make_key(info.author_id) != target)
			]
			if not hits:
				return None
			return JsonDict(max(hits, key=lambda info: str(info.updated_at or "")))

	def taken_over_material_for_user(
		self, user_id: str | int | None) -> JsonDict | None:
		"""该用户的「等截图」被新受理接替后，指向接替它的那条记录。

		用来在用户补发截图时给一句「你的受理已过期，请重新申请」，
		而不是让截图静默消失（见 ``open()`` 的 ``previous_user_id``）。
		"""
		key = str(user_id or "")
		if not key:
			return None
		self._maybe_reload()
		with self._lock:
			for info in self._items.values():
				if (str(info.previous_user_id or "") == key
						and info.status in (self.STATUS_MATERIAL, self.STATUS_REVIEW)):
					return JsonDict(info)
		return None

	def material_remaining(
		self, record: JsonDict, *,
		ttl_minutes: float | None = None) -> float:
		"""「等截图」窗口还剩多少秒；时间缺失 / 已过期返回 0。"""
		moment = parse_iso(str(record.updated_at or ""))
		minutes = (
			ttl_minutes if ttl_minutes is not None
			else self.material_ttl_minutes
		)
		return remaining_seconds(moment, timedelta(minutes=minutes))

	def is_stale(
		self, record: JsonDict, *,
		ttl_minutes: float | None = None) -> bool:
		"""这条「等截图」的申请是否已过期。"""
		return self.material_remaining(record, ttl_minutes=ttl_minutes) <= 0


_default_store: BlackRequestStore | None = None


def get_black_requests() -> BlackRequestStore:
	"""进程内共享的作者下架申请记录。"""
	global _default_store
	if _default_store is None:
		_default_store = BlackRequestStore()
	return _default_store
