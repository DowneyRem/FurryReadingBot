from __future__ import annotations

from sources.base import Novel, Series, Author
from sources.format import format_caption
from sources.linpx.urls import url_novel, url_series, url_author
from sources.linpx.errors import LinpxNotFoundError
from utils.json import JsonDict


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
	
	caption = format_caption(data.desc)
	content = data.content
	like_count = data.pixivLikeCount
	read_count = data.pixivReadCount
	tags = list(data.tags or [])
	images = dict(data.images or {})
	
	create_date = data.createDate
	novel_url = url_novel(novel_id)

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
		novel_url=novel_url,
		raw=data,
	)


def json_to_series(data: dict | JsonDict) -> Series:
	"""解析系列 API 返回的元信息（不含正文）。"""
	data = JsonDict.from_obj(data)
	if not data or data.error:
		raise LinpxNotFoundError("Linpx 上不存在该系列数据", raw=data)

	novel_id = data.novels[0].id if data.novels else ""
	novel_title = data.novels[0].title if data.novels else ""
	series_id = data.novels[0].seriesId if data.novels else ""
	series_title = data.novels[0].seriesTitle if data.novels else ""
	author_id = data.userId
	author_name = data.userName
	
	caption = format_caption(data.caption)
	tags = list(data.tags or [])
	total = int(data.total or 0)
	novels = list(data.novels or [])
	
	for novel in novels:
		tags.extend(novel.tags)
	tags = list(set(tags))
	novel_ids = [novel.id for novel in novels]
	novel_titles = [novel.title for novel in novels]
	
	novel_url = url_novel(novel_id) if novel_id else ""
	series_url = url_series(series_id) if series_id else ""
	
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
		novel_url=novel_url,
		series_url=series_url,
		raw=data
	)


def json_to_author(data: dict | JsonDict) -> Author:
	data = JsonDict.from_obj(data)
	if not data or data.error:
		raise LinpxNotFoundError("Linpx 上不存在该作者数据", raw=data)
	
	novel_id = data.novels[0] if data.novels else ""
	novel_title = ""
	series_id = data.series[0].id if data.series else ""
	series_title = data.series[0].title if data.series else ""
	author_id = data.id
	author_name = data.name
	
	tags = [item.tag for item in data.tags if item.time >= 3]
	comment = data.comment
	image_url = data.imageUrl
	novel_ids = data.novels
	series_ids = [item.id for item in data.series]
	
	novel_url = url_novel(novel_id) if novel_id else ""
	series_url = url_series(series_id) if series_id else ""
	author_url = url_author(author_id)
	
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
		novel_url=novel_url,
		series_url=series_url,
		author_url=author_url,
		raw=data
	)
