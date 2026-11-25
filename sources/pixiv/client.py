"""Pixiv Web API 异步客户端。

只负责：URL 请求、Cookie / 浏览器 Header、全局限流、HTTP 错误映射。
响应解析与模型转换留给 `parse.py`（下一步），这样 client 可以独立测试。
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from infra.http import HttpError, get_json
from sources.pixiv.config import (
	ENV_COOKIE,
	HEADERS,
	LANG,
	MIN_INTERVAL,
)
from sources.pixiv.errors import (
	PixivAuthError,
	PixivNetworkError,
	PixivNotFoundError,
	PixivParseError,
	PixivRateLimitError,
)
from sources.pixiv.urls import (
	url_novel_data,
	url_series_data,
	url_series_novels_title,
	url_user_data,
	url_user_works_all,
)
from utils.json import JsonDict


# 限流状态按事件循环存放：asyncio.Lock 不能跨 loop 复用（测试里每个 asyncio.run 都是新 loop）。
_rate_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}
_rate_last: dict[asyncio.AbstractEventLoop, list[float]] = {}


def _rate_state() -> tuple[asyncio.Lock, list[float]]:
	loop = asyncio.get_running_loop()
	lock = _rate_locks.get(loop)
	if lock is None:
		lock = asyncio.Lock()
		_rate_locks[loop] = lock
	last = _rate_last.get(loop)
	if last is None:
		last = [0.0]
		_rate_last[loop] = last
	return lock, last


def _normalize_cookie(value: str | None) -> str:
	"""完整 Cookie 串原样保留；只给 PHPSESSID 的值时自动补键名。"""
	text = (value or "").strip()
	if not text:
		return ""
	if "=" in text:
		return text
	return f"PHPSESSID={text}"


class PixivClient:
	"""Pixiv Web API（www.pixiv.net/ajax）的异步客户端。"""

	def __init__(
		self,
		cookie: str | None = None,
		*,
		min_interval: float | None = None,
		lang: str = LANG,
	) -> None:
		source = os.environ.get(ENV_COOKIE, "") if cookie is None else cookie
		self._cookie = _normalize_cookie(source)
		self.min_interval = MIN_INTERVAL if min_interval is None else max(0.0, min_interval)
		self.lang = lang or LANG


	@property
	def cookie(self) -> str:
		return self._cookie


	@property
	def has_cookie(self) -> bool:
		"""没有 Cookie 也能读公开作品；R18 正文需要登录态。"""
		return bool(self._cookie)


	def set_cookie(self, cookie: str | None) -> None:
		"""热替换 Cookie：更新 PIXIV_COOKIE 后无需重建 client。"""
		self._cookie = _normalize_cookie(cookie)


	def headers(self) -> dict[str, str]:
		headers = dict(HEADERS)
		if self._cookie:
			headers["Cookie"] = self._cookie
		return headers


	async def _throttle(self) -> None:
		"""请求开始前的最小间隔；只错开开始时间，不串行整个响应。"""
		if self.min_interval <= 0:
			return
		lock, last = _rate_state()
		async with lock:
			now = time.monotonic()
			delay = self.min_interval - (now - last[0])
			if delay > 0:
				await asyncio.sleep(delay)
				now = time.monotonic()
			last[0] = now


	async def _get(self, url: str) -> Any:
		await self._throttle()
		try:
			data = await get_json(url, headers=self.headers())
		except HttpError as e:
			if e.status == 404:
				raise PixivNotFoundError("Pixiv 上不存在该作品", raw=url) from e
			if e.status in (401, 403):
				raise PixivAuthError(
					"Pixiv 登录态失效或无权限，请更新 PIXIV_COOKIE", raw=url) from e
			if e.status == 429:
				raise PixivRateLimitError("Pixiv 请求过于频繁，请稍后重试", raw=url) from e
			raise PixivNetworkError("Pixiv 暂时无法访问，请稍后重试", raw=url) from e
		except ValueError as e:
			raise PixivParseError("Pixiv 返回的数据不是合法 JSON", raw=url) from e
		return data


	async def get_novel(self, novel_id: str | int) -> JsonDict:
		"""小说详情（含正文 `content`；R18 需要 Cookie）。"""
		body = await self._get(url_novel_data(novel_id))
		if not body:
			raise PixivNotFoundError(f"Pixiv 上不存在小说 {novel_id}")
		return JsonDict.from_obj(body)


	async def get_series(self, series_id: str | int) -> JsonDict:
		"""系列详情（元信息，不含章节正文）。"""
		body = await self._get(url_series_data(series_id))
		if not body:
			raise PixivNotFoundError(f"Pixiv 上不存在系列 {series_id}")
		return JsonDict.from_obj(body)


	async def get_series_titles(self, series_id: str | int) -> list[JsonDict]:
		"""系列全部章节 ID + 标题，一次拿完，比逐页拉 content 更省。"""
		payload = await self._get(url_series_novels_title(series_id))
		payload = JsonDict.from_obj(payload)
		# 外壳异常或 error: true 时按「没有章节」处理，交给上层决定要不要报错
		if not isinstance(payload, dict) or payload.error:
			return []
		items = payload.get("body") or []
		if not isinstance(items, list):
			return []
		return [JsonDict.from_obj(item) for item in items if isinstance(item, dict)]


	async def get_author(self, user_id: str | int) -> JsonDict:
		"""作者资料：名字、头像；不含作品列表。"""
		body = await self._get(url_user_data(user_id))
		if not body:
			raise PixivNotFoundError(f"Pixiv 上不存在作者 {user_id}")
		return JsonDict.from_obj(body)


	async def get_author_all(self, user_id: str | int) -> JsonDict:
		"""作者全部作品 ID + 全部系列对象（`novels` / `novelSeries`）。"""
		body = await self._get(url_user_works_all(user_id))
		if not body:
			raise PixivNotFoundError(f"Pixiv 上不存在作者 {user_id}")
		return JsonDict.from_obj(body)
