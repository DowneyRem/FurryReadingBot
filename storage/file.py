#!/usr/bin/python
# -*- coding: UTF-8 -*-
import re
import json
import logging
from os import PathLike
from pathlib import Path
from typing import Any, Iterable

import requests


def remove_file(paths: str | Path | Iterable[str | Path]):
	"""删除多个文件或文件夹"""
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
			logging.error(f"删除失败：{path}，原因：{e}")
		else:
			logging.info(f"已经删除：{path}")


def safe_filename(name: str, max_len: int = 80) -> str:
	name = (name or "untitled").strip()
	name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
	name = re.sub(r"\s+", " ", name).strip(" ._")
	if not name:
		name = "untitled"
	return name[:max_len]


def get_json(url: str, headers: dict | None = None) -> Any:
	"""发送请求并获取 JSON 数据，自带超时与请求头传递"""
	try:
		response = requests.get(url, headers=headers, timeout=15)
		response.raise_for_status()
		return response.json()
	except Exception as e:
		logging.error(f"请求失败：{url}，原因：{e}")
		return None


def download_json(url: str, file_name: str | Path, *, headers: dict | None = None) -> Any:
	"""下载 JSON 并保存到本地"""
	data = get_json(url, headers)
	if data is None:
		return None
	
	save_path = Path(file_name)
	if not save_path.is_absolute():
		save_path = Path(__file__).parent.resolve() / save_path
	return save_json(save_path, data)


def read_text(path: str | Path) -> str:
	"""使用 pathlib 拍平嵌套的多编码文本读取函数"""
	p = Path(path)
	encodings = ["utf-8", "gb18030", "big5", "latin1"]
	
	for encoding in encodings:
		try:
			return p.read_text(encoding=encoding)
		except UnicodeDecodeError:
			continue  # 编码错误则尝试下一个
	logging.error(f"无法以已知编码读取文件：{p}")
	return ""


def read_json(path: str | Path | PathLike) -> Any:
	p = Path(path)
	try:
		return json.loads(p.read_bytes())
	except Exception as e:
		logging.error(f"读取 JSON 失败：{p}，原因：{e}")
		return None


def save_text(path: str | Path | PathLike, text: str = "") -> Path:
	"""使用 pathlib 改造的文本保存函数，自带父目录自动创建功能"""
	p = Path(path)
	try:
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_text(text, encoding="utf-8")
	except Exception as e:
		logging.error(f"保存失败：{p}，原因：{e}")
	else:
		logging.debug(f"已保存为：{p}")
	return p


def save_json(path: str | Path | PathLike, data: Any) -> Path:
	"""使用 pathlib 现代写法保存 JSON，自带父目录自动创建"""
	p = Path(path)
	try:
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_text(
			json.dumps(data, ensure_ascii=False, indent=4),
			encoding="utf-8"
		)
	except Exception as e:
		logging.error(f"保存 JSON 失败：{p}，原因：{e}")
	else:
		logging.debug(f"JSON 已保存为：{p}")
	return p
