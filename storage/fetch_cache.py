"""来源请求缓存：按请求链接（完整 URL）缓存 JSON 响应，减少重复抓取。

下载链路里同一份数据会被请求好几次：`inspect_link` 预检一次、`resolve_link`
解析系列再一次、`packaging.build()` 打包时还要一次。以前每次都打真实网络，
这里把 `infra.http.get_json()` 的响应按 URL 落盘，命中就直接返回：

  - key 直接用请求的链接（含 query 的完整 URL）；
  - 只缓存成功响应，失败照旧抛错，下次仍然重试；
  - TTL 到期自动淘汰，另按条数 / 总字节上限从最旧的开始淘汰，
    避免作者整包（几百章正文）把 JSON 撑大；
  - 写盘同样走 ``JsonStore`` 的原子写与 mtime 热加载。

受限内容（Pixiv R18 未登录时的空正文 / 打码章节）由调用方用
``infra.http.drop_cached_json()`` 显式删掉，不留在缓存里。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from storage.json_store import JsonStore
from utils.json import JsonDict
from utils.time import parse_iso, utc_now, utc_now_iso


logger = logging.getLogger(__name__)


def _expired(info: JsonDict, now: datetime | None = None) -> bool:
	"""没有 ``expires_at`` 或已到期的条目都算过期。"""
	expires = parse_iso(str(info.expires_at or ""))
	if expires is None:
		return True
	return (now or utc_now()) >= expires


class FetchCacheStore(JsonStore):
	"""请求 URL -> JSON 响应的缓存；单条记录带 TTL、写入序号与字节数。"""

	DATA_KEY = "responses"
	# 单条响应的硬上限：Chapter 正文再长也不该超过它，否则直接不缓存
	DEFAULT_MAX_BYTES = 2 * 1024 * 1024
	DEFAULT_MAX_ENTRIES = 200

	def __init__(
		self,
		path: Path | None = None,
		*,
		default_ttl_hours: float | None = None,
		max_bytes: int | None = None,
		max_entries: int | None = None,
	) -> None:
		if path is None:
			path = Path(__file__).parent.parent.resolve() / "data" / "fetch_cache.json"
		# 默认值只在 config 里定义；0 也是合法值（立即过期），不能用 or 兜底
		if default_ttl_hours is None:
			from config import FETCH_CACHE_TTL_HOURS

			default_ttl_hours = FETCH_CACHE_TTL_HOURS
		self.default_ttl_hours = default_ttl_hours
		self.max_bytes = self.DEFAULT_MAX_BYTES if max_bytes is None else max_bytes
		self.max_entries = self.DEFAULT_MAX_ENTRIES if max_entries is None else max_entries
		# 下面 super().__init__ 会触发 reload -> _prune，上限必须先就位
		super().__init__(path)

	def _normalize(self, info: Any) -> JsonDict | None:
		if not isinstance(info, dict):
			return None
		payload = info.get("payload")
		if payload is None:
			return None
		return JsonDict(
			payload=payload,
			size=int(info.get("size") or 0),
			# 写入序号：淘汰时按它判断新旧（同一秒内写入也能分出先后）
			seq=int(info.get("seq") or 0),
			cached_at=str(info.get("cached_at") or ""),
			expires_at=str(info.get("expires_at") or ""),
		)

	def _prune(self) -> None:
		"""先丢过期条目，再按条数 / 总字节上限从最旧的开始淘汰。"""
		now = utc_now()
		for key, info in list(self._items.items()):
			if _expired(info, now):
				del self._items[key]
		if self._within_limits():
			return
		for key in self._oldest_first():
			if self._within_limits():
				break
			del self._items[key]

	def _within_limits(self) -> bool:
		return (
			len(self._items) <= self.max_entries
			and self._total_size() <= self.max_bytes
		)

	def _total_size(self) -> int:
		return sum(int(info.size or 0) for info in self._items.values())

	def _oldest_first(self) -> list[str]:
		return sorted(self._items, key=lambda key: int(self._items[key].seq or 0))

	def get(self, key: str) -> Any | None:
		"""命中且未过期时返回缓存的 JSON；过期条目顺手清掉。"""
		self._maybe_reload()
		with self._lock:
			name = str(key)
			info = self._items.get(name)
			if info is None:
				return None
			if _expired(info):
				del self._items[name]
				self._persist()
				return None
			return info.payload

	def set(self, key: str, payload: Any) -> bool:
		"""写入一条响应；``None`` / 不可序列化 / 单条超过总上限时跳过并返回 False。"""
		if payload is None:
			return False
		try:
			size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
		except (TypeError, ValueError):
			logger.debug("响应不是可缓存的 JSON，跳过：%s", key)
			return False
		if size > self.max_bytes:
			logger.debug("响应超过缓存上限（%d 字节），跳过：%s", size, key)
			return False

		now = utc_now()
		expires = now + timedelta(hours=self.default_ttl_hours)
		with self._lock:
			self._maybe_reload()
			seq = max(
				(int(info.seq or 0) for info in self._items.values()), default=0
			) + 1
			self._items[str(key)] = JsonDict(
				payload=payload,
				size=size,
				seq=seq,
				cached_at=utc_now_iso(),
				expires_at=expires.strftime("%Y-%m-%dT%H:%M:%S%z"),
			)
			self._persist()
		return True

	def remove(self, key: str) -> bool:
		with self._lock:
			self._maybe_reload()
			name = str(key)
			if name not in self._items:
				return False
			del self._items[name]
			self._persist()
			return True


_default_cache: FetchCacheStore | None = None


def get_fetch_cache() -> FetchCacheStore:
	"""进程内共享的请求缓存；TTL 走 config.FETCH_CACHE_TTL_HOURS。"""
	global _default_cache
	if _default_cache is None:
		_default_cache = FetchCacheStore()
	return _default_cache


def peek_fetch_cache() -> FetchCacheStore | None:
	"""已经创建过的请求缓存实例；没创建过返回 None。

	「删掉某条缓存」这种场景不需要为了删除而先把缓存建出来，
	调用方据此在缓存未启用时直接跳过。
	"""
	return _default_cache

