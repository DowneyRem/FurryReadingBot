"""HTTP 访问：aiohttp 按事件循环复用会话，requests 作为同步兜底。"""

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


async def get_json(url: str, headers: dict | None = None) -> Any | None:
	"""异步获取 JSON；失败返回 ``None``，调用方按空值处理。"""
	try:
		session = _get_session()
		async with session.get(url, headers=headers) as resp:
			resp.raise_for_status()
			return await resp.json()
	except Exception as e:
		logger.error("异步请求 JSON 失败：%s，原因：%s", url, e)
		return None


def get_json_sync(url: str, headers: dict | None = None) -> Any | None:
	"""同步获取 JSON；失败返回 ``None``，供独立脚本使用。"""
	try:
		response = requests.get(url, headers=headers, timeout=SYNC_TIMEOUT)
		response.raise_for_status()
		return response.json()
	except Exception as e:
		logger.error("请求失败：%s，原因：%s", url, e)
		return None


async def download_json(
	url: str,
	file_name: str | Path,
	*,
	headers: dict | None = None,
) -> Any | None:
	"""下载 JSON 并保存到本地。"""
	data = await get_json(url, headers=headers)
	if data is None:
		return None
	await save_json(Path(file_name), data)
	return data


def download_json_sync(
	url: str,
	file_name: str | Path,
	*,
	headers: dict | None = None,
) -> Any | None:
	"""同步下载 JSON 并保存到本地。"""
	data = get_json_sync(url, headers=headers)
	if data is None:
		return None
	save_json_sync(Path(file_name), data)
	return data
