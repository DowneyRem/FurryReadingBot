from __future__ import annotations

import re
from sources.base import Novel
from sources.linpx.urls import url_novel
from sources.linpx.config import NOVEL_PATTERN
from sources.linpx.config import NOVEL_PATTERN, SERIES_PATTERN, AUTHOR_PATTERN
from utils.json import JsonDict


def get_novel_id(text: str) -> str | None:
	m = re.compile(NOVEL_PATTERN, re.I).search(text)
	if m:
		return m.group(1)
	return None

def get_series_id(text: str) -> str | None:
	"""从文本中解析系列 ID"""
	m = re.compile(SERIES_PATTERN, re.I).search(text)
	if m:
		return m.group(1)
	return None

def get_author_id(text: str) -> str | None:
	"""从文本中解析系列 ID"""
	m = re.compile(AUTHOR_PATTERN, re.I).search(text)
	if m:
		return m.group(1)
	return None


def is_novel_link(text: str) -> bool:
	return get_novel_id(text) is not None

def is_series_link(text: str) -> bool:
	return get_series_id(text) is not None

def is_author_link(text: str) -> bool:
	return get_author_id(text) is not None

def is_linpx_link(text: str) -> bool:
	"""是否为可处理的单篇或系列链接。"""
	return is_novel_link(text) or is_series_link(text) or is_author_link(text)


def json_to_novel(data: dict | JsonDict) -> Novel:
	data = JsonDict.from_obj(data)
	if not data or data.error:
		raise ValueError(data.error or "Linpx 返回错误或空数据")

	novel_id = str(data.id or data._id or "")
	title = (data.title or "").strip()
	author_id = str(data.userId or "")
	author_name = (data.userName or "").strip()
	content = data.content or ""
	tags = list(data.tags or [])
	desc = data.desc or data.description or ""
	create_date = data.createDate or ""

	series_id = None
	series_title = None
	series = data.series
	if isinstance(series, dict) and series.id:
		series_id = str(series.id)
		series_title = (series.title or "").strip() or None

	url = url_novel(novel_id)

	return Novel(
		id=novel_id,
		title=title,
		author_id=author_id,
		author_name=author_name,
		content=content,
		tags=tags,
		description=desc,
		series_id=series_id,
		series_title=series_title,
		source="linpx",
		url=url,
		create_date=create_date,
		raw=data,
	)