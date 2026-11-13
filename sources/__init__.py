from __future__ import annotations

from sources.base import Author, Novel, NovelSource, Series
from sources.linpx import LinpxSource
from sources.linpx.urls import url_author, url_novel, url_series

_SOURCES: list[NovelSource] = [
	LinpxSource(),
]


def work_url(kind: str, item_id: str | int) -> str:
	"""按作品类型拼出 Linpx 作品链接。

	分享链路只拿到 `kind;item_id`（callback_data 里没有链接），
	file_id 缓存里又没存 link 的老数据靠这里兜底。
	"""
	if not item_id:
		return ""
	if kind == "series":
		return url_series(item_id)
	if kind == "author":
		return url_author(item_id)
	return url_novel(item_id)


def resolve_source(link: str) -> NovelSource | None:
	for source in _SOURCES:
		if source.can_handle(link):
			return source
	return None


def _require_source(link: str) -> NovelSource:
	source = resolve_source(link)
	if source is None:
		raise ValueError(f"暂不支持该链接：{link}")
	return source


async def fetch(link: str) -> Novel | Series | Author:
	source = _require_source(link)
	if source.is_novel_link(link):
		return await source.fetch_novel(link)
	elif source.is_series_link(link):
		return await source.fetch_series(link)
	else:
		return await source.fetch_author(link)


async def resolve_link(link: str, kind: str) -> str:
	source = _require_source(link)
	if kind == "series" and source.is_novel_link(link):
		novel = await source.fetch_novel(link)
		return novel.series_url or link
	else:
		return link
