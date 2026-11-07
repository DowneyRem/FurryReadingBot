from __future__ import annotations

import re
from sources.base import Novel
from sources.linpx.urls import url_novel
from sources.linpx.config import NOVEL_PATTERN
from sources.linpx.errors import LinpxNotFoundError
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


def s(v) -> str:
	return str(v or "").strip()

def json_to_novel(data: dict | JsonDict) -> Novel:
	data = JsonDict.from_obj(data)
	if not data or data.error:
		raise LinpxNotFoundError("Linpx 上不存在该小说数据", raw=data)
	
	novel_id = data.id
	novel_title = data.title
	if data.series:
		series_id = s(data.series.id) or None
		series_title = s(data.series.title) or None
	else:
		series_id = None
		series_title = None
	author_id = data.userId
	author_name = data.userName

	content = data.content
	tags = list(data.tags or [])
	desc = data.desc
	create_date = data.createDate

	return Novel(
		id=novel_id,
		title=novel_title,
		series_id=series_id,
		series_title=series_title,
		author_id=author_id,
		author_name = author_name,
		
		content=content,
		tags=tags,
		description=desc,
		url=url_novel(novel_id),
		create_date=create_date,
		
		source="linpx",
		raw=data,
	)