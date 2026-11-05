#!/usr/bin/python
# -*- coding: UTF-8 -*-
import json
import logging
from pathlib import Path

from os import PathLike
from typing import Any


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