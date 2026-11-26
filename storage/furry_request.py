"""兽人作者名单申请记录：JSON 文件存储，支持热加载。

同一作者 1 天内只能申请一次（``config.APPLY_COOLDOWN_HOURS``）：
``last_apply_at`` 只记录「提交申请」的时间，审核改状态不会刷新它。

已结束（通过 / 拒绝）的记录按 ``config.FURRY_REQUEST_TTL_DAYS`` 保留，
到期在 ``_prune()`` 里整条删掉，文件不会随审核历史无限增长；
还在流程里的 ``pending`` 记录**不按 TTL 淘汰**，否则待审核的申请会凭空消失。
名单本身在 ``furry_authors.json``，记录被淘汰不影响作者权限。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from storage.request_store import AuthorRequestStore
from utils.json import JsonDict, to_int
from utils.time import utc_now_iso


class FurryRequestStore(AuthorRequestStore):
	"""待审核的「申请加入兽人作者名单」记录，key 为 author_id。"""

	DATA_KEY = "furry_request"
	RECORD_TTL_CONFIG = "FURRY_REQUEST_TTL_DAYS"

	STATUS_PENDING = "pending"
	DEFAULT_STATUS = STATUS_PENDING

	def __init__(
		self,
		path: Path | None = None,
		*,
		apply_cooldown_hours: float | None = None,
		record_ttl_days: float | None = None,
	) -> None:
		if path is None:
			path = Path(__file__).parent.parent.resolve() / "data" / "furry_request.json"
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
			link=str(info.get("link") or ""),
			user_id=str(info.get("user_id") or ""),
			user_name=str(info.get("user_name") or ""),
			status=str(info.get("status") or self.STATUS_PENDING),
			created_at=str(info.get("created_at") or ""),
			last_apply_at=str(info.get("last_apply_at") or ""),
			updated_at=str(info.get("updated_at") or ""),
			count=to_int(info.get("count")),
			note=str(info.get("note") or ""),
		)

	def is_pending(self, author_id: str | int) -> bool:
		info = self.get(author_id)
		return bool(info) and info.status == self.STATUS_PENDING

	def submit(
		self,
		author_id: str | int,
		*,
		author_name: str = "",
		link: str = "",
		user_id: str | int | None = None,
		user_name: str = "",
		note: str = "",
	) -> JsonDict:
		"""写入 / 更新一条待审核申请，返回最新记录。"""
		now = utc_now_iso()
		with self._lock:
			self._maybe_reload()
			key = self.make_key(author_id)
			prev = self._items.get(key) or JsonDict()
			self._items[key] = JsonDict(
				author_id=key,
				author_name=str(author_name or prev.author_name or ""),
				link=str(link or prev.link or ""),
				user_id=str(user_id or prev.user_id or ""),
				user_name=str(user_name or prev.user_name or ""),
				# 重新发起申请时回到待审核
				status=self.STATUS_PENDING,
				created_at=str(prev.created_at or now),
				last_apply_at=now,
				updated_at=now,
				count=to_int(prev.count) + 1,
				note=str(note or prev.note or ""),
			)
			self._persist()
			return JsonDict(self._items[key])

_default_store: FurryRequestStore | None = None


def get_furry_requests() -> FurryRequestStore:
	"""进程内共享的兽人作者申请记录：申请与核验共用同一份数据。"""
	global _default_store
	if _default_store is None:
		_default_store = FurryRequestStore()
	return _default_store

