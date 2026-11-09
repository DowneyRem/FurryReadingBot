from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from utils.json import JsonDict


def _utc_now() -> datetime:
	return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
	return _utc_now().strftime("%Y-%m-%dT%H:%M:%S%z")


def _parse_iso(s: str) -> datetime | None:
	if not s:
		return None
	try:
		s = s.strip()
		if len(s) >= 5 and (s[-5] in "+-" and s[-3] != ":"):
			s = s[:-2] + ":" + s[-2:]
		return datetime.fromisoformat(s)
	except Exception:
		return None


def _as_id_list(value: str | int | Iterable[str | int] | None) -> list[str]:
	if value is None:
		return []
	if isinstance(value, (str, int)):
		return [str(value)]
	return [str(v) for v in value]


class ShareRecordStore:
	"""分享记录：按 kind:id 记录分享情况，支持冷却窗口与 TTL，热加载。

	与 FileCacheStore 的区别：
	  - key 是 "{kind}:{item_id}"，不含 file_type，同一作品的 txt / zip 共用一条记录；
	  - 冷却窗口（cooldown）可配置，记录保留时间（ttl）固定为 DEFAULT_TTL_DAYS，互不影响；
	  - 记录里保留分享者 / 频道 / 次数，便于统计与审计。
	"""
	
	DEFAULT_COOLDOWN_DAYS = 7
	# 记录保留时间写死在代码里，不提供配置入口
	DEFAULT_TTL_DAYS = 30


	def __init__(
		self,
		path: Path | None = None,
		cooldown_days: float | None = None,
	) -> None:
		if path is None:
			path = Path(__file__).parent.parent.resolve() / "data" / "share_records.json"
		self.path = path
		self.cooldown_days = (
			cooldown_days if cooldown_days is not None else self.DEFAULT_COOLDOWN_DAYS
		)
		self._lock = threading.RLock()
		self._mtime: float = 0.0
		self._shares: JsonDict = JsonDict()
		self.path.parent.mkdir(parents=True, exist_ok=True)
		if not self.path.exists():
			self._write_empty()
		self.reload(force=True)


	def _write_empty(self) -> None:
		payload = JsonDict(updated_at=_utc_now_iso(), shares=JsonDict())
		self.path.write_text(
			json.dumps(payload, ensure_ascii=False, indent=4),
			encoding="utf-8",
		)


	@staticmethod
	def _normalize(info: dict) -> JsonDict:
		return JsonDict(
			kind=str(info.get("kind") or ""),
			item_id=str(info.get("item_id") or ""),
			title=str(info.get("title") or ""),
			first_shared_at=str(info.get("first_shared_at") or ""),
			last_shared_at=str(info.get("last_shared_at") or ""),
			expires_at=str(info.get("expires_at") or ""),
			count=int(info.get("count") or 0),
			last_user_id=str(info.get("last_user_id") or ""),
			last_user_name=str(info.get("last_user_name") or ""),
			last_chat_ids=_as_id_list(info.get("last_chat_ids")),
			last_file_type=str(info.get("last_file_type") or ""),
			public=bool(info.get("public", True)),
		)


	def reload(self, force: bool = False) -> bool:
		with self._lock:
			if not self.path.exists():
				self._write_empty()
				return True
			mtime = self.path.stat().st_mtime
			if not force and mtime == self._mtime:
				return False
			data = JsonDict.from_obj(json.loads(self.path.read_text(encoding="utf-8")))
			raw = data.shares or JsonDict()
			shares = JsonDict()
			for key, info in raw.items():
				key = str(key)
				if isinstance(info, dict):
					shares[key] = self._normalize(info)
			self._shares = shares
			self._mtime = mtime
			self._prune()
			return True


	def _maybe_reload(self) -> None:
		if self.path.exists() and self.path.stat().st_mtime != self._mtime:
			self.reload(force=True)


	def _persist(self) -> None:
		self._prune()
		payload = JsonDict(
			updated_at=_utc_now_iso(),
			shares=JsonDict({k: self._shares[k] for k in sorted(self._shares.keys())}),
		)
		self.path.write_text(
			json.dumps(payload, ensure_ascii=False, indent=4),
			encoding="utf-8",
		)
		self._mtime = self.path.stat().st_mtime


	def _prune(self) -> None:
		"""丢弃超过保留时间的记录，避免文件无限增长。"""
		now = _utc_now()
		expired = [
			key for key, info in self._shares.items()
			if (exp := _parse_iso(info.expires_at)) is not None and now >= exp
		]
		for key in expired:
			del self._shares[key]


	@staticmethod
	def make_key(kind: str, item_id: str | int) -> str:
		return f"{kind}:{item_id}"


	def get(self, key: str) -> JsonDict | None:
		"""返回未过期的分享记录，没有则返回 None。"""
		self._maybe_reload()
		with self._lock:
			k = str(key)
			info = self._shares.get(k)
			if not info:
				return None
			exp = _parse_iso(info.expires_at)
			if exp is not None and _utc_now() >= exp:
				del self._shares[k]
				self._persist()
				return None
			return info


	def remaining(self, key: str, *, cooldown_days: float | None = None) -> float:
		"""距离冷却结束还剩多少秒；0 表示当前可以分享。"""
		info = self.get(key)
		if not info:
			return 0.0
		last = _parse_iso(info.last_shared_at)
		if last is None:
			return 0.0
		days = cooldown_days if cooldown_days is not None else self.cooldown_days
		left = (last + timedelta(days=days) - _utc_now()).total_seconds()
		return max(0.0, left)


	def is_limited(self, key: str, *, cooldown_days: float | None = None) -> bool:
		return self.remaining(key, cooldown_days=cooldown_days) > 0


	def record(
		self,
		key: str,
		*,
		kind: str = "",
		item_id: str | int = "",
		title: str = "",
		user_id: str | int | None = None,
		user_name: str = "",
		chat_ids: str | int | Iterable[str | int] | None = None,
		file_type: str = "",
		public: bool = True,
	) -> JsonDict:
		"""写入 / 更新一条分享记录，返回最新记录。"""
		now = _utc_now()
		with self._lock:
			self._maybe_reload()
			k = str(key)
			prev = self._shares.get(k) or JsonDict()
			self._shares[k] = JsonDict(
				kind=str(kind or prev.kind or ""),
				item_id=str(item_id or prev.item_id or ""),
				title=str(title or prev.title or ""),
				first_shared_at=str(prev.first_shared_at or now.strftime("%Y-%m-%dT%H:%M:%S%z")),
				last_shared_at=now.strftime("%Y-%m-%dT%H:%M:%S%z"),
				expires_at=(now + timedelta(days=self.DEFAULT_TTL_DAYS)).strftime("%Y-%m-%dT%H:%M:%S%z"),
				count=int(prev.count or 0) + 1,
				last_user_id=str(user_id or ""),
				last_user_name=str(user_name or ""),
				last_chat_ids=_as_id_list(chat_ids),
				last_file_type=str(file_type or ""),
				public=bool(public),
			)
			self._persist()
			return self._shares[k]


	def remove(self, key: str) -> bool:
		with self._lock:
			self._maybe_reload()
			k = str(key)
			if k not in self._shares:
				return False
			del self._shares[k]
			self._persist()
			return True


	def records(self) -> JsonDict:
		"""返回全部有效记录的浅拷贝，便于统计 / 管理端展示。"""
		self._maybe_reload()
		with self._lock:
			self._prune()
			return JsonDict(dict(self._shares))

