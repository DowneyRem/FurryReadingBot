from __future__ import annotations

from sources.base import Novel, Series, Author
from sources.format import format_caption, format_pixiv_content
from sources.pixiv.urls import url_novel, url_series, url_author
from sources.pixiv.errors import PixivNotFoundError
from utils.json import JsonDict


def _embedded_image_urls(value: object) -> dict[str, str]:
	"""`textEmbeddedImages` → `{图片ID: 原图URL}`；缺失或结构异常时返回空表。"""
	data = JsonDict.from_obj(value)
	if not isinstance(data, dict):
		return {}
	urls: dict[str, str] = {}
	for key, item in data.items():
		url = item.urls.original if isinstance(item, dict) else None
		if url:
			urls[str(key)] = str(url)
	return urls


def json_to_novel(data: dict | JsonDict) -> Novel:
	data = JsonDict.from_obj(data)
	if not data or data.error:
		raise PixivNotFoundError("Pixiv 上不存在该小说数据", raw=data)
	data = data.body
	if not data:
		raise PixivNotFoundError("Pixiv 上不存在该小说数据", raw=data)
	
	novel_id = data.id
	novel_url = url_novel(novel_id)
	novel_title = data.title or ""
	
	series_nav = data.seriesNavData
	series_id = (series_nav.seriesId if series_nav else None) or None
	series_url = url_series(series_id) if series_id else None
	series_title = (series_nav.title if series_nav else None) or None
	
	author_id = data.userId
	author_url = url_author(author_id)
	author_name = data.userName or ""
	
	caption = format_caption(data.description)
	content = data.content
	# content = format_pixiv_content(
	# 	data.content or "", _embedded_image_urls(data.textEmbeddedImages))
	tags = [item.tag for item in data.tags.tags]
	
	like_count = int(data.bookmarkCount or 0)
	read_count = int(data.viewCount or 0)
	comment_count = int(data.commentCount or 0)
	
	images = data.coverUrl
	create_date = data.createDate
	
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


def json_to_series(data: dict | JsonDict) -> Series:
	data = JsonDict.from_obj(data)
	if not data or data.error:
		raise PixivNotFoundError("Pixiv 上不存在该系列数据", raw=data)
	data = data.body
	if not data:
		raise PixivNotFoundError("Pixiv 上不存在该系列数据", raw=data)
	
	novel_id = data.firstNovelId or ""
	novel_url = url_novel(novel_id) if novel_id else ""
	novel_title = ""

	series_id = data.id
	series_url = url_series(series_id)
	series_title = data.title or ""
	
	author_id = data.userId
	author_url = url_author(author_id)
	author_name = data.userName or ""
	
	caption = format_caption(data.caption)
	tags = data.tags or []
	# total = data.total
	total = int(data.publishedContentCount or 0)
	
	return Series(
		novel_id = novel_id,
		novel_url = novel_url,
		novel_title = novel_title,
		
		series_id = series_id,
		series_url = series_url,
		series_title = series_title,
		
		author_id = author_id,
		author_url = author_url,
		author_name = author_name,
		
		caption=caption,
		tags=tags,
		total=total,
		
		source="Pixiv",
		raw=data
	)


def json_to_author(
	profile: dict | JsonDict,
	works: dict | JsonDict | None = None,
) -> Author:
	"""作者资料 + 全部作品：Pixiv 把 profile / profile_all 拆成了两个接口。"""
	profile = JsonDict.from_obj(profile)
	if not profile or profile.error:
		raise PixivNotFoundError("Pixiv 上不存在该作者数据", raw=profile)
	profile = JsonDict.from_obj(profile.body)
	if not profile:
		raise PixivNotFoundError("Pixiv 上不存在该作者数据", raw=profile)

	works = JsonDict.from_obj(JsonDict.from_obj(works or {}).get("body") or {})

	novel_ids = [str(novel_id) for novel_id in (works.novels or {})]
	novel_id = novel_ids[0] if novel_ids else ""
	novel_url = url_novel(novel_id) if novel_id else ""
	novel_title = ""

	series = list(works.novelSeries or [])
	series_ids = [str(item.id) for item in series]
	series_id = series_ids[0] if series_ids else None
	series_url = url_series(series_id) if series_id else None
	series_title = series[0].title if series else None

	author_id = profile.userId
	author_url = url_author(author_id)
	author_name = profile.name or ""

	comment = format_caption(profile.comment)
	image_url = profile.image or ""

	return Author(
		novel_id=novel_id,
		novel_url=novel_url,
		novel_title=novel_title,

		series_id=series_id,
		series_url=series_url,
		series_title=series_title,

		author_id=author_id,
		author_url=author_url,
		author_name=author_name,

		comment=comment,
		image_url=image_url,
		novel_ids=novel_ids,
		series_ids=series_ids,

		source="Pixiv",
		raw=profile
	)
