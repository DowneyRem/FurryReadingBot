"""兽人作者名单申请记录：JSON 文件存储，支持热加载。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from storage.json_store import JsonStore
from utils.json import JsonDict
from utils.time import utc_now_iso


class FurryRequestStore(JsonStore):
	"""待审核的「申请加入兽人作者名单」记录，key 为 author_id。"""

	DATA_KEY = "furry_request"

	STATUS_PENDING = "pending"
	STATUS_APPROVED = "approved"
	STATUS_REJECTED = "rejected"

	def __init__(self, path: Path | None = None) -> None:
		if path is None:
			path = Path(__file__).parent.parent.resolve() / "data" / "furry_request.json"
		super().__init__(path)

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
				updated_at=now,
				count=int(prev.count or 0) + 1,
				note=str(note or prev.note or ""),
			)
			self._persist()
			return JsonDict(self._items[key])

	def set_status(
		self, author_id: str | int, status: str,
		*, expected: str | None = None) -> bool:
		"""更新申请状态；``expected`` 用于保证并发核验只有一个能生效。"""
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

	def remove(self, author_id: str | int) -> bool:
		with self._lock:
			self._maybe_reload()
			key = self.make_key(author_id)
			if key not in self._items:
				return False
			del self._items[key]
			self._persist()
			return True

	def records(self) -> JsonDict:
		"""返回全部申请记录的浅拷贝，便于管理端展示。"""
		self._maybe_reload()
		with self._lock:
			return JsonDict(dict(self._items))
