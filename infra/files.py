"""文件读写工具：同步实现 + 异步包装，运行时统一走异步接口。

原来 ``storage/file.py`` 与 ``storage/file_async.py`` 是两份镜像实现，
现在只保留一套同步核心，异步接口通过 ``asyncio.to_thread`` 包装。

报错约定（只用 Python 内置异常，不自定义）：
	- 只捕获真正预期的类型：``OSError``（含 ``FileNotFoundError``）/ ``UnicodeError`` / ``ValueError``；
	- 原样上抛，保留 ``errno`` / ``filename`` 和原始 traceback，调用方按需判断；
	- 日志统一「<动作>失败：<完整路径>」并带 ``exc_info``，路径与 errno 由 traceback 带出；
	- 读失败沿用旧契约（返回 ``""`` / ``None``），调用方按空值处理；
	- 写失败必须抛：否则调用方会把半成品当产物上传，坏文件还会进 ``file_id`` 缓存。
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
	"""删除多个文件或文件夹。尽力而为：单个失败只记日志，不影响其余文件。"""
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
		except FileNotFoundError:
			logger.debug("删除跳过：%s（文件已不存在）", path)
		except OSError:
			logger.error("删除失败：%s", path, exc_info=True)
		else:
			logger.info("已经删除：%s", path)


async def remove_file(paths: str | Path | Iterable[str | Path]) -> None:
	"""异步删除文件/文件夹，不阻塞主线程。"""
	await asyncio.to_thread(remove_file_sync, paths)


def read_text_sync(path: str | Path) -> str:
	"""按常见编码依次尝试读取文本；读不到返回空串（调用方按空值处理）。"""
	p = Path(path)
	encodings = ["utf-8", "gb18030", "big5", "latin1"]

	for encoding in encodings:
		try:
			return p.read_text(encoding=encoding)
		except UnicodeDecodeError:
			continue
		except FileNotFoundError:
			logger.error("读取文本失败：%s（文件不存在）", p)
			return ""
		except OSError:
			logger.error("读取文本失败：%s", p, exc_info=True)
			return ""

	logger.error("读取文本失败：%s（utf-8 / gb18030 / big5 / latin1 均解码失败）", p)
	return ""


async def read_txt(path: str | Path | PathLike) -> str:
	"""异步读取文本。"""
	return await asyncio.to_thread(read_text_sync, path)


def read_json_sync(path: str | Path | PathLike) -> Any:
	"""读取 JSON；读不到或格式非法返回 ``None``，原因写进日志。"""
	p = Path(path)
	try:
		return json.loads(p.read_bytes())
	except FileNotFoundError:
		logger.error("读取 JSON 失败：%s（文件不存在）", p)
		return None
	except OSError:
		logger.error("读取 JSON 失败：%s", p, exc_info=True)
		return None
	except ValueError:  # json.JSONDecodeError 是其子类
		logger.error("读取 JSON 失败：%s（内容不是合法 JSON）", p, exc_info=True)
		return None


async def read_json(path: str | Path | PathLike) -> Any:
	"""异步读取 JSON。"""
	return await asyncio.to_thread(read_json_sync, path)


def save_text_sync(path: str | Path | PathLike, text: str = "") -> Path:
	"""保存文本，自动创建父目录。

	写失败原样抛 ``OSError``（``errno`` / ``filename`` / traceback 都保留）：
	调用方不能把这个路径当成成功产物去上传，否则坏文件会进 ``file_id`` 缓存，
	之后 TTL 内一直被复用。
	"""
	p = Path(path)
	try:
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_text(text, encoding="utf-8")
	except (OSError, UnicodeError):
		logger.error("保存文本失败：%s", p, exc_info=True)
		raise
	logger.debug("已保存为：%s", p)
	return p


async def save_text(path: str | Path | PathLike, text: str = "") -> Path:
	"""异步保存文本，自动创建父目录。失败原样抛 ``OSError``。"""
	return await asyncio.to_thread(save_text_sync, path, text)


def save_json_sync(path: str | Path | PathLike, data: Any) -> Path:
	"""保存 JSON，自动创建父目录。序列化或写盘失败都原样抛出。"""
	p = Path(path)
	try:
		payload = json.dumps(data, ensure_ascii=False, indent=4)
	except (TypeError, ValueError):
		logger.error("序列化 JSON 失败：%s", p, exc_info=True)
		raise

	try:
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_text(payload, encoding="utf-8")
	except (OSError, UnicodeError):
		logger.error("保存 JSON 失败：%s", p, exc_info=True)
		raise
	logger.debug("JSON 已保存为：%s", p)
	return p


async def save_json(path: str | Path | PathLike, data: Any) -> Path:
	"""异步保存 JSON，自动创建父目录。失败原样抛出。"""
	return await asyncio.to_thread(save_json_sync, path, data)
