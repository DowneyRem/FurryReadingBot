"""HTTP 访问：aiohttp 按事件循环复用会话；requests 只给独立脚本用。

``get_json()`` 默认带请求缓存（``storage/fetch_cache.py``）：key 就是请求的链接，
成功响应落盘后在 TTL 内直接复用，失败照旧抛错、下次重试。
同一个作品在「预检 → 解析系列 → 打包」里被请求多次时，只有第一次真正打网络。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp
import requests

from infra.files import save_json, save_json_sync

if TYPE_CHECKING:
	from storage.fetch_cache import FetchCacheStore


logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
SYNC_TIMEOUT = 15

# aiohttp 的 ClientSession 绑定事件循环；按 loop 缓存，避免跨 loop 复用。
_sessions: dict[asyncio.AbstractEventLoop, aiohttp.ClientSession] = {}


def _get_session() -> aiohttp.ClientSession:
	loop = asyncio.get_running_loop()
	session = _sessions.get(loop)
	if session is None or session.closed:
		session = aiohttp.ClientSession(
			timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT))
		_sessions[loop] = session
	return session


async def close_http() -> None:
	"""关闭当前事件循环上的 aiohttp 会话（bot shutdown / 测试收尾）。"""
	loop = asyncio.get_running_loop()
	session = _sessions.pop(loop, None)
	if session is not None and not session.closed:
		await session.close()


class HttpError(Exception):
	"""请求最终失败：status 为 None 表示没拿到响应（超时、连接失败）。"""

	def __init__(self, url: str, status: int | None = None) -> None:
		self.url = url
		self.status = status
		super().__init__(f"请求失败（{status or '无响应'}）：{url}")


RETRY_ATTEMPTS = 3
RETRY_DELAY = 1.0


def _is_retryable(status: int, *, retry_on_429: bool = True) -> bool:
	if status == 429:
		return retry_on_429
	return status >= 500


async def _request(
	url: str,
	headers: dict | None = None,
	*,
	retry_on_429: bool = True,
	as_json: bool = True,
) -> Any:
	"""异步请求公共重试骨架；超时、连接失败、429（可选）/ 5xx 自动重试，最终失败抛 ``HttpError``。"""
	status: int | None = None
	for attempt in range(1, RETRY_ATTEMPTS + 1):
		try:
			session = _get_session()
			async with session.get(url, headers=headers) as resp:
				status = resp.status
				if resp.status < 400:
					return await (resp.json() if as_json else resp.text())
				if not _is_retryable(resp.status, retry_on_429=retry_on_429):
					raise HttpError(url, resp.status)
		except (aiohttp.ClientError, asyncio.TimeoutError) as e:
			status = None
			logger.warning("请求%s失败（第 %d 次）：%s，原因：%s", " JSON " if as_json else "文本", attempt, url, e)
		else:
			logger.warning("请求%s失败（第 %d 次）：%s，状态：%s", " JSON " if as_json else "文本", attempt, url, status)
		if attempt < RETRY_ATTEMPTS:
			await asyncio.sleep(RETRY_DELAY * attempt)
	raise HttpError(url, status)


# ----- 请求缓存 -----
def _cache() -> "FetchCacheStore | None":
	"""取进程内请求缓存；不可用时返回 None，让请求降级为直连。

	缓存坏了（JSON 损坏、磁盘只读）只该少一层加速，不能让下载整体失败，
	所以这里连同后面的读写一起兜异常。
	"""
	try:
		# 延迟导入：infra 只在真正要用缓存时才依赖 storage，避免导入期互相牵连
		from storage.fetch_cache import get_fetch_cache

		return get_fetch_cache()
	except Exception as error:
		logger.warning("请求缓存不可用，本次直接请求：%s", error)
		return None


def _cached(cache: "FetchCacheStore", url: str) -> Any | None:
	try:
		return cache.get(url)
	except Exception as error:
		logger.warning("读取请求缓存失败，本次直接请求：%s（%s）", url, error)
		return None


def _remember(cache: "FetchCacheStore", url: str, data: Any) -> None:
	try:
		cache.set(url, data)
	except Exception as error:
		logger.warning("写入请求缓存失败：%s（%s）", url, error)


def drop_cached_json(url: str) -> bool:
	"""删掉某个 URL 的请求缓存，返回是否真的删了一条。

	给「响应不能用」的场景用：例如 Pixiv 未登录时 R18 正文为空 / 章节被打码，
	这份响应不能留给之后配好 Cookie 的请求。缓存没创建过时直接跳过，
	不为了一次删除先把缓存文件建出来。
	"""
	try:
		# 延迟导入：infra 只在真正要用缓存时才依赖 storage，避免导入期互相牵连
		from storage.fetch_cache import peek_fetch_cache

		cache = peek_fetch_cache()
	except Exception as error:
		logger.warning("请求缓存不可用，跳过清理：%s（%s）", url, error)
		return False
	if cache is None:
		return False
	try:
		return cache.remove(url)
	except Exception as error:
		logger.warning("清理请求缓存失败：%s（%s）", url, error)
		return False


async def get_json(
	url: str,
	headers: dict | None = None,
	*,
	retry_on_429: bool = True,
	use_cache: bool = True,
) -> Any:
	"""异步获取 JSON；超时、连接失败、429（可选）/ 5xx 自动重试，最终失败抛 ``HttpError``。

	默认按 URL 走请求缓存（``storage/fetch_cache.py``）：命中直接返回，
	成功响应回写，失败不写（下次仍然重试）。确实要最新数据时传 ``use_cache=False``。
	"""
	cache = _cache() if use_cache else None
	if cache is not None:
		cached = _cached(cache, url)
		if cached is not None:
			logger.debug("命中请求缓存：%s", url)
			return cached

	data = await _request(url, headers=headers, retry_on_429=retry_on_429, as_json=True)
	if cache is not None:
		_remember(cache, url, data)
	return data


async def get_text(
	url: str,
	headers: dict | None = None,
	*,
	retry_on_429: bool = True,
) -> str:
	"""异步获取文本（HTML 等）；重试与报错约定同 ``get_json``。"""
	return await _request(url, headers=headers, retry_on_429=retry_on_429, as_json=False)


def get_json_sync(url: str, headers: dict | None = None) -> Any:
	"""同步获取 JSON，供独立脚本使用；失败直接抛出。"""
	response = requests.get(url, headers=headers, timeout=SYNC_TIMEOUT)
	response.raise_for_status()
	return response.json()


async def download_json(
	url: str,
	file_name: str | Path,
	*,
	headers: dict | None = None,
) -> Any:
	"""下载 JSON 并保存到本地。"""
	data = await get_json(url, headers=headers)
	await save_json(Path(file_name), data)
	return data


def download_json_sync(
	url: str,
	file_name: str | Path,
	*,
	headers: dict | None = None,
) -> Any:
	"""同步下载 JSON 并保存到本地。"""
	data = get_json_sync(url, headers=headers)
	save_json_sync(Path(file_name), data)
	return data
