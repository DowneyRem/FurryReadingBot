from __future__ import annotations

from sources.base import Novel, Series, Author
from sources.format import format_caption
from sources.pixiv.urls import url_novel, url_series, url_author
from sources.pixiv.errors import PixivNotFoundError
from utils.json import JsonDict


def json_to_novel(data: dict | JsonDict) -> Novel:
	data = JsonDict.from_obj(data)
	if not data or data.error:
		raise PixivNotFoundError("Pixiv 上不存在该小说数据", raw=data)
	data = data.body
	
	novel_id = data.id
	novel_url = url_novel(novel_id)
	novel_title = data.title
	
	series_id = data.seriesNavData.seriesId or None
	series_url = url_series(series_id) or None
	series_title = data.seriesNavData.title or None
	
	author_id = data.userId
	author_url = url_author(author_id)
	author_name = data.userName
	
	caption = format_caption(data.description)
	content = data.content
	tags = [item.tag for item in data.tags]
	
	like_count = data.bookmarkCount
	read_count = data.viewCount
	comment_count = data.commentCount
	
	images = data.coverUrl
	create_date = data.createDate
	update_date = data.updateDate
	lang = data.language
	
	return Novel(
		novel_id = novel_id,
		novel_url = novel_url,
		novel_title=novel_title,
		
		series_id = series_id,
		series_url = series_url,
		series_title = series_title,
		
		author_id = author_id,
		author_url = author_url,
		author_name = author_name,
		
		caption = caption,
		content = content,
		tags = tags,
		
		like_count = like_count,
		read_count = read_count,
		comment_count = comment_count,
		
		images = images,
		create_date = create_date,
		
		source="Pixiv",
		raw=data
	)