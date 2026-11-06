#!/usr/bin/python
# -*- coding: UTF-8 -*-
import json
import logging
from os import PathLike
from pathlib import Path
from typing import Any, Iterable
import asyncio

import aiofiles
import aiohttp

# 调整日志格式，方便异步调试
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def remove_file(paths: str | Path | Iterable[str | Path]) -> None:
	"""异步删除文件/文件夹，不阻塞主线程"""
	from storage.file import remove_file as remove_file_sync
	await asyncio.to_thread(remove_file_sync, paths)


async def get_json(url: str, headers: dict | None = None) -> dict | None:
	"""网络请求：自带会话与超时管理，错误安全兜底"""
	# aiohttp 强烈建议在实例化 ClientSession 时就带上 timeout，或者在 get 里传
	timeout = aiohttp.ClientTimeout(total=30)
	try:
		async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
			async with session.get(url) as resp:
				resp.raise_for_status()
				return await resp.json()
	except Exception as e:
		logging.error(f"异步请求 JSON 失败：{url}，原因：{e}")
		return None


async def download_json(url: str, file_name: str | Path, *, headers: dict | None = None) -> Any:
	"""下载 JSON 并智能保存到本地（支持绝对路径/相对路径）"""
	data = await get_json(url, headers)
	if data is None:
		return None
	
	save_path = Path(file_name)
	if not save_path.is_absolute():
		save_path = Path(__file__).parent.resolve() / save_path
	
	await save_json(save_path, data)
	return data


async def read_txt(path: PathLike) -> str:
	text = ""
	try:
		async with aiofiles.open(path, "r", encoding="UTF8") as f:
			text = await f.read()
	except UnicodeError:
		try:
			async with aiofiles.open(path, "r", encoding="GB18030") as f:
				text = await f.read()
		except UnicodeError:
			try:
				async with aiofiles.open(path, "r", encoding="BIG5") as f:
					text = await f.read()
			except UnicodeError:
				async with aiofiles.open(path, "r", encoding="Latin1") as f:
					text = await f.read()
	finally:
		return text


async def read_json(path: PathLike) -> Any:
	try:
		async with aiofiles.open(path, "rb") as f:
			content = await f.read()
			data = json.loads(content)
	except IOError as e:
		logging.error(e)
	else:
		return data


async def save_text(path: PathLike, text: str = "") -> PathLike:
	try:
		async with aiofiles.open(path, "w", encoding="UTF8") as f:
			await f.write(text)
	except IOError:
		logging.error(f"保存失败：{path}")
	else:
		logging.debug(f"已保存为：{path}")
	return path


async def save_json(path: PathLike, data: Any) -> PathLike:
	try:
		async with aiofiles.open(path, "w", encoding="UTF8") as f:
			await f.write(json.dumps(data, ensure_ascii=False, indent=4))
	except IOError:
		logging.error(f"保存失败：{path}")
	else:
		logging.debug(f"已保存为：{path}")
	return Path(path)

# 调用时需要使用 await，例如：
# content = await read_txt("example.txt")
# data = await read_json("data.json")
# await save_text("out.txt", "hello")
# await save_json("out.json", {"a": 1})