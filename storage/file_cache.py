"""Telegram file_id 缓存：按业务 key 存储，支持 TTL，热加载。"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from storage.json_store import JsonStore
from utils.json import JsonDict
from utils.time import parse_iso, utc_now


class FileCacheStore(JsonStore):
	"""
	统一缓存 4 种下载产物，key 格式：
	  novel:{id}:txt
	  series:{id}:txt
	  series:{id}:zip
	  author:{id}:zip
	"""

	DATA_KEY = "files"
	DEFAULT_TTL_DAYS = 30

	def __init__(self, path: Path | None = None, default_ttl_days: float | None = None) -> None:
		if path is None:
			path = Path(__file__).parent.parent.resolve() / "data" / "files_cache.json"
		# bot 内由 config.FILE_CACHE_TTL_DAYS 覆盖；0 也是合法值，不能用 or 兜底
		self.default_ttl_days = (
			self.DEFAULT_TTL_DAYS if default_ttl_days is None else default_ttl_days
		)
		super().__init__(path)

	def _normalize(self, info: Any) -> JsonDict | None:
		if not isinstance(info, dict):
			return None
		return JsonDict(
			file_id=str(info.get("file_id") or ""),
			file_name=str(info.get("file_name") or ""),
			caption=str(info.get("caption") or ""),
			author_id=str(info.get("author_id") or ""),
			author_name=str(info.get("author_name") or ""),
			uploaded_at=str(info.get("uploaded_at") or ""),
			expires_at=str(info.get("expires_at") or ""),
		)

	def _prune(self) -> None:
		"""丢弃已过期的缓存条目，避免文件无限增长。"""
		now = utc_now()
		expired = [
			key for key, info in self._items.items()
			if (exp := parse_iso(info.expires_at)) is not None and now >= exp
		]
		for key in expired:
			del self._items[key]

	@staticmethod
	def make_key(kind: str, item_id: str, file_type: str) -> str:
		return f"{kind}:{item_id}:{file_type}"

	def get_valid(self, key: str) -> JsonDict | None:
		self._maybe_reload()
		with self._lock:
			info = self._items.get(str(key))
			if not info or not info.file_id:
				return None
			exp = parse_iso(info.expires_at)
			if exp is not None and utc_now() >= exp:
				del self._items[str(key)]
				self._persist()
				return None
			return info

	def set(
		self,
		key: str,
		file_id: str,
		*,
		file_name: str = "",
		caption: str = "",
		author_id: str | int = "",
		author_name: str = "",
	) -> None:
		if not file_id:
			return
		now = utc_now()
		expires = now + timedelta(days=self.default_ttl_days)
		with self._lock:
			self._maybe_reload()
			self._items[str(key)] = JsonDict(
				file_id=file_id,
				file_name=file_name or "",
				caption=caption or "",
				author_id=str(author_id or ""),
				author_name=author_name or "",
				uploaded_at=now.strftime("%Y-%m-%dT%H:%M:%S%z"),
				expires_at=expires.strftime("%Y-%m-%dT%H:%M:%S%z"),
			)
			self._persist()

	def remove(self, key: str) -> bool:
		with self._lock:
			self._maybe_reload()
			k = str(key)
			if k not in self._items:
				return False
			del self._items[k]
			self._persist()
			return True


_default_cache: FileCacheStore | None = None


def get_file_cache() -> FileCacheStore:
	"""进程内共享的 file_id 缓存；TTL 由 config 控制。"""
	global _default_cache
	if _default_cache is None:
		from config import FILE_CACHE_TTL_DAYS

		_default_cache = FileCacheStore(default_ttl_days=FILE_CACHE_TTL_DAYS)
	return _default_cache
