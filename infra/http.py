"""HTTP 访问：aiohttp 按事件循环复用会话；requests 只给独立脚本用。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiohttp
import requests

from infra.files import save_json, save_json_sync

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


async def get_json(
	url: str,
	headers: dict | None = None,
	*,
	retry_on_429: bool = True,
) -> Any:
	"""异步获取 JSON；超时、连接失败、429（可选）/ 5xx 自动重试，最终失败抛 ``HttpError``。"""
	return await _request(url, headers=headers, retry_on_429=retry_on_429, as_json=True)


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
