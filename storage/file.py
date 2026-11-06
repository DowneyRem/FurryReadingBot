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


def get_json(url: str, headers) -> Any:
	response = requests.get(url, timeout=15)
	response.raise_for_status()
	return response.json()


def download_json(url: str, file_name: str, *, headers) -> Any:
	"""下载 JSON 并可选保存到本地"""
	data = get_json(url, headers)
	save_path = Path(__file__).parent.resolve() / file_name
	save_json(data, save_path)
	return data


def read_txt(path: PathLike) -> str:
	text = ""
	try:
		with open(path, "r", encoding="UTF8") as f:
			text = f.read()
	except UnicodeError:
		try:
			with open(path, "r", encoding="GB18030") as f:
				text = f.read()
		except UnicodeError:
			try:
				with open(path, "r", encoding="BIG5") as f:
					text = f.read()
			except UnicodeError:
				with open(path, "r", encoding="Latin1") as f:
					text = f.read()
	finally:
		return text


def read_json(path: PathLike) -> Any:
	try:
		with open(path, "rb") as f:
			data = json.load(f)
	except IOError as e:
		logging.error(e)
	else:
		return data


def save_text(path: PathLike, text: str="") -> PathLike:
	try:
		with open(path, "w", encoding="UTF8") as f:
			f.write(text)
	except IOError:
		logging.error(f"保存失败：{path}")
	else:
		logging.debug(f"已保存为：{path}")
	return path


def save_json(path: PathLike, data: Any) -> PathLike:
	try:
		with open(path, 'w', encoding="UTF8") as f:
			json.dump(data, f, ensure_ascii=False, indent=4)
	except IOError:
		logging.error(f"保存失败：{path}")
	else:
		logging.debug(f"已保存为：{path}")
	return Path(path)