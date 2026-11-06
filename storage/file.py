#!/usr/bin/python
# -*- coding: UTF-8 -*-
import json
import logging
from os import PathLike
from pathlib import Path
from typing import Any

import requests


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