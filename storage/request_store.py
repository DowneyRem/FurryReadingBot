"""作者申请类 Store 的公共部分：key 为 ``author_id`` 的读写、状态流转与 TTL 淘汰。

``FurryRequestStore``（申请加入兽人作者名单）与 ``BlackRequestStore``（作者申请下架）
只差状态名和各自的业务方法，下面这些操作两边完全一样，所以收在这里：

  - ``make_key`` / ``get`` / ``records``（key 归一 + 浅拷贝），``remove`` 由 ``JsonStore`` 提供；
  - ``apply_remaining``（``APPLY_COOLDOWN_HOURS`` 冷却剩余秒数）；
  - ``set_status``（``expected`` 保证并发核验只有一个能生效）；
  - ``_prune``（只淘汰已结束的 ``approved`` / ``rejected``，按 ``record_ttl_days``）。

子类要给：``DATA_KEY``、``RECORD_TTL_CONFIG``（config 里 TTL 常量的名字）、
``DEFAULT_STATUS``（记录缺 ``status`` 字段时按什么状态算），以及自己的 ``_normalize``。
"""

from __future__ import annotations

from pathlib import Path

from storage.json_store import JsonStore, config_default
from utils.json import JsonDict
from utils.time import cooldown_left, is_older_than, parse_iso, utc_now_iso


class AuthorRequestStore(JsonStore):
	"""key 为 ``author_id`` 的申请记录：公共读写 + 状态流转 + TTL 淘汰。"""

	STATUS_APPROVED = "approved"
	STATUS_REJECTED = "rejected"
	# 已经走完流程的状态：只有这些记录会按 record_ttl_days 淘汰
	CLOSED_STATUSES = (STATUS_APPROVED, STATUS_REJECTED)
	# 子类必须覆盖
	RECORD_TTL_CONFIG = ""
	DEFAULT_STATUS = ""

	def __init__(
		self,
		path: Path,
		*,
		apply_cooldown_hours: float | None = None,
		record_ttl_days: float | None = None,
	) -> None:
		# 默认值只在 config 里定义；0 也是合法值（不冷却 / 立即过期），不能用 or 兜底
		self.apply_cooldown_hours = config_default(
			apply_cooldown_hours, "APPLY_COOLDOWN_HOURS")
		self.record_ttl_days = config_default(
			record_ttl_days, self.RECORD_TTL_CONFIG)
		super().__init__(path)

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
		return cooldown_left(
			str(info.last_apply_at or ""), self.apply_cooldown_hours)

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

	def records(self) -> JsonDict:
		"""全部申请记录的浅拷贝，便于管理端展示。"""
		self._maybe_reload()
		with self._lock:
			return JsonDict(dict(self._items))

	def _prune(self) -> None:
		"""删掉已结束且超过 ``record_ttl_days`` 的申请记录。

		只淘汰 ``CLOSED_STATUSES``：还在流程里的申请不能按 TTL 删——待审核的
		不能凭空消失，等截图的过期后要被下一位申请人接手（见 ``black_request``）。
		``updated_at`` 解析不出来的旧数据同样保留，不静默丢申请凭据。
		"""
		for key, info in list(self._items.items()):
			status = str(info.get("status") or self.DEFAULT_STATUS)
			if status not in self.CLOSED_STATUSES:
				continue
			if is_older_than(
				parse_iso(str(info.get("updated_at") or "")),
				self.record_ttl_days,
			):
				del self._items[key]
