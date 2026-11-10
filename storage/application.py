"""兽人作者白名单申请记录：JSON 文件存储，支持热加载。"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from storage.utils import utc_now_iso
from utils.json import JsonDict


class ApplicationStore:
	"""待审核的「申请加入兽人作者名单」记录，key 为 author_id。

	与 AuthorListStore 一样采用文件存储 + 热加载：
	管理员可以直接编辑 data/applications.json，运行时无需重启。
	中转频道与管理员核验接入后，只需在此基础上更新 status 字段。
	"""
	
	STATUS_PENDING = "pending"
	STATUS_APPROVED = "approved"
	STATUS_REJECTED = "rejected"


	def __init__(self, path: Path | None = None) -> None:
		if path is None:
			path = Path(__file__).parent.parent.resolve() / "data" / "applications.json"
		self.path = path
		self._lock = threading.RLock()
		self._mtime: float = 0.0
		self._applications: JsonDict = JsonDict()
		self.path.parent.mkdir(parents=True, exist_ok=True)
		if not self.path.exists():
			self._write_empty()
		self.reload(force=True)


	def _write_empty(self) -> None:
		payload = JsonDict(updated_at=utc_now_iso(), applications=JsonDict())
		self.path.write_text(
			json.dumps(payload, ensure_ascii=False, indent=4),
			encoding="utf-8",
		)


	@staticmethod
	def _normalize(info: dict) -> JsonDict:
		return JsonDict(
			author_id=str(info.get("author_id") or ""),
			author_name=str(info.get("author_name") or ""),
			link=str(info.get("link") or ""),
			kind=str(info.get("kind") or ""),
			user_id=str(info.get("user_id") or ""),
			user_name=str(info.get("user_name") or ""),
			status=str(info.get("status") or ApplicationStore.STATUS_PENDING),
			created_at=str(info.get("created_at") or ""),
			updated_at=str(info.get("updated_at") or ""),
			count=int(info.get("count") or 0),
			note=str(info.get("note") or ""),
		)


	def reload(self, force: bool = False) -> bool:
		"""文件有变更时重新加载。返回是否真的读了磁盘。"""
		with self._lock:
			if not self.path.exists():
				self._write_empty()
				return True
			mtime = self.path.stat().st_mtime
			if not force and mtime == self._mtime:
				return False
			data = JsonDict.from_obj(json.loads(self.path.read_text(encoding="utf-8")))
			raw = data.applications or JsonDict()
			applications = JsonDict()
			for key, info in raw.items():
				key = str(key)
				if isinstance(info, dict):
					applications[key] = self._normalize(info)
			self._applications = applications
			self._mtime = mtime
			return True


	def _maybe_reload(self) -> None:
		if self.path.exists() and self.path.stat().st_mtime != self._mtime:
			self.reload(force=True)


	def _persist(self) -> None:
		payload = JsonDict(
			updated_at=utc_now_iso(),
			applications=JsonDict(
				{k: self._applications[k] for k in sorted(self._applications.keys())}
			),
		)
		self.path.write_text(
			json.dumps(payload, ensure_ascii=False, indent=4),
			encoding="utf-8",
		)
		self._mtime = self.path.stat().st_mtime


	@staticmethod
	def make_key(author_id: str | int) -> str:
		return str(author_id)


	def get(self, author_id: str | int) -> JsonDict | None:
		"""返回该作者的申请记录，没有则返回 None。"""
		self._maybe_reload()
		with self._lock:
			info = self._applications.get(self.make_key(author_id))
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
		kind: str = "",
		user_id: str | int | None = None,
		user_name: str = "",
		note: str = "",
	) -> JsonDict:
		"""写入 / 更新一条待审核申请，返回最新记录。"""
		now = utc_now_iso()
		with self._lock:
			self._maybe_reload()
			key = self.make_key(author_id)
			prev = self._applications.get(key) or JsonDict()
			self._applications[key] = JsonDict(
				author_id=key,
				author_name=str(author_name or prev.author_name or ""),
				link=str(link or prev.link or ""),
				kind=str(kind or prev.kind or ""),
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
			return JsonDict(self._applications[key])


	def set_status(self, author_id: str | int, status: str) -> bool:
		"""更新申请状态（审核通过 / 拒绝后调用）。"""
		with self._lock:
			self._maybe_reload()
			key = self.make_key(author_id)
			if key not in self._applications:
				return False
			self._applications[key] = JsonDict({
				**self._applications[key],
				"status": status,
				"updated_at": utc_now_iso(),
			})
			self._persist()
			return True


	def remove(self, author_id: str | int) -> bool:
		with self._lock:
			self._maybe_reload()
			key = self.make_key(author_id)
			if key not in self._applications:
				return False
			del self._applications[key]
			self._persist()
			return True


	def records(self) -> JsonDict:
		"""返回全部申请记录的浅拷贝，便于管理端展示。"""
		self._maybe_reload()
		with self._lock:
			return JsonDict(dict(self._applications))
