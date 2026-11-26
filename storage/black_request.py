"""作者拉黑申请：作者本人提交后台截图，管理员核验后加入黑名单。

	作者主页链接 → 点「申请下架」→ 提交截图 → 中转频道核验 → 拉黑

状态流转：

	pending_material（等截图） → pending_review（等管理员） → approved / rejected

key 为 author_id：一个作者一条记录，重复申请只累计 ``count``。
「等截图」有时限（``config.BLACK_REQUEST_MATERIAL_TTL_MINUTES``），过期后要重新点申请。
同一作者 1 天内只能申请一次（``config.APPLY_COOLDOWN_HOURS``）：冷却按
``last_apply_at``（提交截图送审的时间）算，只受理不交截图不受影响。
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from storage.json_store import JsonStore
from utils.json import JsonDict
from utils.time import (
	cooldown_remaining,
	parse_iso,
	utc_now,
	utc_now_iso,
)


class BlackRequestStore(JsonStore):
	"""作者下架申请记录，key 为 author_id。"""

	DATA_KEY = "black_request"

	STATUS_MATERIAL = "pending_material"
	STATUS_REVIEW = "pending_review"
	STATUS_APPROVED = "approved"
	STATUS_REJECTED = "rejected"

	# 点完申请后，多久内提交截图仍然有效
	# 具体分钟数只在 config 里定义（BLACK_REQUEST_MATERIAL_TTL_MINUTES）

	def __init__(
		self,
		path: Path | None = None,
		*,
		material_ttl_minutes: float | None = None,
		apply_cooldown_hours: float | None = None,
	) -> None:
		if path is None:
			path = (
				Path(__file__).parent.parent.resolve()
				/ "data" / "black_request.json"
			)
		# 默认值只在 config 里定义；0 也是合法值（立即过期），不能用 or 兜底
		if material_ttl_minutes is None:
			from config import BLACK_REQUEST_MATERIAL_TTL_MINUTES

			material_ttl_minutes = BLACK_REQUEST_MATERIAL_TTL_MINUTES
		if apply_cooldown_hours is None:
			from config import APPLY_COOLDOWN_HOURS

			apply_cooldown_hours = APPLY_COOLDOWN_HOURS
		self.material_ttl_minutes = material_ttl_minutes
		self.apply_cooldown_hours = apply_cooldown_hours
		super().__init__(path)

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
			count=int(info.get("count") or 0),
			note=str(info.get("note") or ""),
		)

	@staticmethod
	def make_key(author_id: str | int) -> str:
		return str(author_id)

	def get(self, author_id: str | int) -> JsonDict | None:
		"""返回该作者的申请记录，没有则返回 None。"""
		self._maybe_reload()
		with self._lock:
			info = self._items.get(self.make_key(author_id))
			return JsonDict(info) if info else None

	def apply_remaining(self, author_id: str | int) -> float:
		"""距离该作者下次可申请还剩多少秒；0 表示现在就能申请。"""
		info = self.get(author_id)
		if not info:
			return 0.0
		return cooldown_remaining(
			parse_iso(str(info.last_apply_at or "")), self.apply_cooldown_hours)

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
		"""
		now = utc_now_iso()
		with self._lock:
			self._maybe_reload()
			key = self.make_key(author_id)
			prev = self._items.get(key) or JsonDict()
			self._items[key] = JsonDict(
				author_id=key,
				author_name=str(author_name or prev.author_name or ""),
				author_url=str(author_url or prev.author_url or ""),
				user_id=str(user_id or prev.user_id or ""),
				user_name=str(user_name or prev.user_name or ""),
				status=self.STATUS_MATERIAL,
				photo_file_id="",
				created_at=str(prev.created_at or now),
				last_apply_at=str(prev.last_apply_at or ""),
				updated_at=now,
				count=int(prev.count or 0) + 1,
				note="",
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

	def set_status(
		self, author_id: str | int, status: str,
		*, expected: str | None = None) -> bool:
		"""更新申请状态；``expected`` 保证并发核验只有一个能生效。"""
		with self._lock:
			self._maybe_reload()
			key = self.make_key(author_id)
			current = self._items.get(key)
			if current is None:
				return False
			if expected is not None and str(current.status or "") != expected:
				return False
			self._items[key] = JsonDict({
				**current,
				"status": status,
				"updated_at": utc_now_iso(),
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
		"""该用户最近一条「等截图」的申请（不判断是否过期）。"""
		key = str(user_id or "")
		if not key:
			return None
		self._maybe_reload()
		with self._lock:
			hits = [
				info for info in self._items.values()
				if str(info.user_id or "") == key
				and info.status == self.STATUS_MATERIAL
			]
			if not hits:
				return None
			return JsonDict(max(hits, key=lambda info: str(info.updated_at or "")))

	def is_stale(
		self, record: JsonDict, *,
		ttl_minutes: float | None = None) -> bool:
		"""这条「等截图」的申请是否已过期。"""
		moment = parse_iso(str(record.updated_at or ""))
		if moment is None:
			return True
		minutes = (
			ttl_minutes if ttl_minutes is not None
			else self.material_ttl_minutes
		)
		return utc_now() - moment > timedelta(minutes=minutes)

	def records(self) -> JsonDict:
		"""全部申请记录的浅拷贝，便于统计 / 管理端展示。"""
		self._maybe_reload()
		with self._lock:
			return JsonDict(dict(self._items))


_default_store: BlackRequestStore | None = None


def get_black_requests() -> BlackRequestStore:
	"""进程内共享的作者下架申请记录。"""
	global _default_store
	if _default_store is None:
		_default_store = BlackRequestStore()
	return _default_store
