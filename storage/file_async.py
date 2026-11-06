#!/usr/bin/python
# -*- coding: UTF-8 -*-
import json
import logging
from os import PathLike
from pathlib import Path
from typing import Any

import aiofiles
import aiohttp


async def get_json(url: str, headers) -> dict:
	async with aiohttp.ClientSession(headers=headers) as session:
		async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
			resp.raise_for_status()
			data = await resp.json()
			return data


async def download_json(url: str, file_name: str, *, headers) -> Any:
	data = await get_json(url, headers)
	save_path = Path(__file__).parent.resolve() / file_name
	await save_json(save_path, data)          # 注意：保持和你原来一样的参数顺序
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