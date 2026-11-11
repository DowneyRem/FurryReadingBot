"""文件读写工具：同步实现 + 异步包装，运行时统一走异步接口。

原来 ``storage/file.py`` 与 ``storage/file_async.py`` 是两份镜像实现，
现在只保留一套同步核心，异步接口通过 ``asyncio.to_thread`` 包装。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from os import PathLike
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def safe_filename(name: str, max_len: int = 80) -> str:
	"""把标题清洗成可安全落盘的文件名。"""
	name = (name or "untitled").strip()
	name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
	name = re.sub(r"\s+", " ", name).strip(" ._")
	if not name:
		name = "untitled"
	return name[:max_len]


def remove_file_sync(paths: str | Path | Iterable[str | Path]) -> None:
	"""删除多个文件或文件夹。"""
	if isinstance(paths, (str, Path)):
		paths = [paths]

	for p in paths:
		path = Path(p)
		try:
			if path.is_dir():
				import shutil

				shutil.rmtree(path)
			elif path.is_file() or path.is_symlink():
				path.unlink()
		except Exception as e:
			logger.error("删除失败：%s，原因：%s", path, e)
		else:
			logger.info("已经删除：%s", path)


async def remove_file(paths: str | Path | Iterable[str | Path]) -> None:
	"""异步删除文件/文件夹，不阻塞主线程。"""
	await asyncio.to_thread(remove_file_sync, paths)


def read_text_sync(path: str | Path) -> str:
	"""按常见编码依次尝试读取文本。"""
	p = Path(path)
	encodings = ["utf-8", "gb18030", "big5", "latin1"]

	for encoding in encodings:
		try:
			return p.read_text(encoding=encoding)
		except UnicodeDecodeError:
			continue
		except FileNotFoundError:
			logger.error("文件不存在：%s", p)
			return ""
	logger.error("无法以已知编码读取文件：%s", p)
	return ""


async def read_txt(path: str | Path | PathLike) -> str:
	"""异步读取文本。"""
	return await asyncio.to_thread(read_text_sync, path)


def read_json_sync(path: str | Path | PathLike) -> Any:
	p = Path(path)
	try:
		return json.loads(p.read_bytes())
	except Exception as e:
		logger.error("读取 JSON 失败：%s，原因：%s", p, e)
		return None


async def read_json(path: str | Path | PathLike) -> Any:
	"""异步读取 JSON。"""
	return await asyncio.to_thread(read_json_sync, path)


def save_text_sync(path: str | Path | PathLike, text: str = "") -> Path:
	"""保存文本，自动创建父目录。"""
	p = Path(path)
	try:
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_text(text, encoding="utf-8")
	except Exception as e:
		logger.error("保存失败：%s，原因：%s", p, e)
	else:
		logger.debug("已保存为：%s", p)
	return p


async def save_text(path: str | Path | PathLike, text: str = "") -> Path:
	"""异步保存文本，自动创建父目录。"""
	return await asyncio.to_thread(save_text_sync, path, text)


def save_json_sync(path: str | Path | PathLike, data: Any) -> Path:
	"""保存 JSON，自动创建父目录。"""
	p = Path(path)
	try:
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_text(
			json.dumps(data, ensure_ascii=False, indent=4),
			encoding="utf-8",
		)
	except Exception as e:
		logger.error("保存 JSON 失败：%s，原因：%s", p, e)
	else:
		logger.debug("JSON 已保存为：%s", p)
	return p


async def save_json(path: str | Path | PathLike, data: Any) -> Path:
	"""异步保存 JSON，自动创建父目录。"""
	return await asyncio.to_thread(save_json_sync, path, data)
