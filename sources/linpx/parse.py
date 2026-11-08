from __future__ import annotations

import re
from sources.base import Novel, Series, Author
from sources.linpx.urls import url_novel, url_series, url_author
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


def json_to_novel(data: dict | JsonDict) -> Novel:
	data = JsonDict.from_obj(data)
	if not data or data.error:
		raise LinpxNotFoundError("Linpx 上不存在该小说数据", raw=data)
	
	novel_id = data.id
	novel_title = data.title
	if data.series:
		series_id = data.series.id
		series_title = data.series.title
	else:
		series_id = None
		series_title = None
	author_id = data.userId
	author_name = data.userName
	
	caption = data.desc
	content = data.content
	like_count = data.pixivLikeCount
	read_count = data.pixivReadCount
	tags = list(data.tags or [])
	images = dict(data.images or {})
	
	create_date = data.createDate

	return Novel(
		novel_id=novel_id,
		novel_title=novel_title,
		series_id=series_id,
		series_title=series_title,
		author_id=author_id,
		author_name = author_name,
		
		caption=caption,
		content=content,
		like_count=like_count,
		read_count=read_count,
		create_date=create_date,
		tags=tags,
		images=images,
		
		source="Linpx",
		url=url_novel(novel_id),
		raw=data,
	)


def json_to_series(data: dict | JsonDict) -> Series:
	"""解析系列 API 返回的元信息（不含正文）。"""
	data = JsonDict.from_obj(data)
	if not data or data.error:
		raise LinpxNotFoundError("Linpx 上不存在该系列数据", raw=data)

	novel_id = data.novels[0].id
	novel_title = data.novels[0].title
	series_id = data.novels[0].seriesId
	series_title = data.novels[0].seriesTitle
	author_id = data.userId
	author_name = data.userName
	
	caption = (data.caption or data.desc or "").strip()
	tags = list(data.tags or [])
	total = int(data.total or 0)
	novels = list(data.novels or [])
	
	for novel in novels:
		tags.extend(novel.tags)
	tags = list(set(tags))
	novel_ids = [novel.id for novel in novels]
	novel_titles = [novel.title for novel in novels]
	
	return Series(
		novel_id=novel_id,
		novel_title=novel_title,
		series_id=series_id,
		series_title=series_title,
		author_id=author_id,
		author_name=author_name,
		
		caption=caption,
		tags=tags,
		total=total,
		novel_ids=novel_ids,
		novel_titles=novel_titles,
		
		source="Linpx",
		url=url_series(series_id),
		novel_url=url_novel(novel_id),
		raw=data
	)


def json_to_author(data: dict | JsonDict) -> Author:
	data = JsonDict.from_obj(data)
	if not data or data.error:
		raise LinpxNotFoundError("Linpx 上不存在该系列数据", raw=data)
	
	novel_id = data.novels[0]
	novel_title = ""
	series_id = data.series[0].id
	series_title = data.series[0].title
	author_id = data.id
	author_name = data.name
	
	tags = [tag.tag for tag in data.tags]
	comment = data.comment
	image_url = data.imageUrl
	novel_ids = data.novels
	series_ids = [series.id for series in data.series]
	
	return Author(
		novel_id=novel_id,
		novel_title=novel_title,
		series_id=series_id,
		series_title=series_title,
		author_id=author_id,
		author_name=author_name,
		
		tags=tags,
		comment=comment,
		image_url=image_url,
		novel_ids=novel_ids,
		series_ids=series_ids,
		
		source="Linpx",
		url=url_author(author_id),
		novel_url=url_novel(novel_id),
		raw=data
	)


def format_chapter_title(chapter_title: str, series_title: str, index: int) -> str:
	"""生成章节标题：去掉与系列名重复的部分，并补上「第N章」。"""
	title = (chapter_title or "").strip()
	series = (series_title or "").strip()
	if series:
		replaced = title.replace(series, "").replace("-", "").strip()
		if len(replaced) >= 2:
			title = replaced
	if "第" not in title and "章" not in title:
		title = f"第{index}章 {title}"
	return title

