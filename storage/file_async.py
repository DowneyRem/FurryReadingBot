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
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


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


async def read_txt(path: str | Path | PathLike) -> str:
	"""利用循环拍平‘金字塔嵌套’的异步多编码文本读取"""
	p = Path(path)
	encodings = ["utf-8", "gb18030", "big5", "latin1"]
	
	for encoding in encodings:
		try:
			async with aiofiles.open(p, "r", encoding=encoding) as f:
				return await f.read()
		except UnicodeDecodeError:
			continue
		except FileNotFoundError as e:
			logging.error(f"文件不存在：{p}")
			break
	return ""


async def read_json(path: str | Path | PathLike) -> Any:
	"""修复原代码局部变量 data 未定义的异步 JSON 读取"""
	p = Path(path)
	try:
		async with aiofiles.open(p, "rb") as f:
			content = await f.read()
			return json.loads(content)
	except Exception as e:
		logging.error(f"异步读取 JSON 失败：{p}，原因：{e}")
		return None


async def save_text(path: str | Path | PathLike, text: str = "") -> Path:
	"""自动创建父级目录的异步文本保存"""
	p = Path(path)
	try:
		p.parent.mkdir(parents=True, exist_ok=True)
		async with aiofiles.open(p, "w", encoding="utf-8") as f:
			await f.write(text)
	except Exception as e:
		logging.error(f"异步保存文本失败：{p}，原因：{e}")
	else:
		logging.info(f"已保存为：{p}")
	return p


async def save_json(path: str | Path | PathLike, data: Any) -> Path:
	"""自动创建父级目录的异步 JSON 保存"""
	p = Path(path)
	try:
		p.parent.mkdir(parents=True, exist_ok=True)
		async with aiofiles.open(p, "w", encoding="utf-8") as f:
			# 提前在内存中算好 json 字符串（同步），再整体塞给异步文件流
			serialized_data = json.dumps(data, ensure_ascii=False, indent=4)
			await f.write(serialized_data)
	except Exception as e:
		logging.error(f"异步保存 JSON 失败：{p}，原因：{e}")
	else:
		logging.info(f"已保存为：{p}")
	return p
