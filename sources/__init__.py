from __future__ import annotations

from pathlib import Path

from sources.base import Author, Novel, NovelSource, Series
from sources.linpx import LinpxSource

_SOURCES: list[NovelSource] = [
	LinpxSource(),
]


def resolve_source(link: str) -> NovelSource | None:
	for source in _SOURCES:
		if source.can_handle(link):
			return source
	return None


async def fetch(link: str) -> Novel | Series | Author:
	source = resolve_source(link)
	if source.is_novel_link(link):
		return await source.fetch_novel(link)
	elif source.is_series_link(link):
		return await source.fetch_series(link)
	else:
		return await source.fetch_author(link)


async def save(link: str, ext: str="") -> Path:
	source = resolve_source(link)
	if source.is_novel_link(link):
		return await source.save_novel(link)
	elif source.is_series_link(link):
		if ext == "txt":
			return await source.save_series_txt(link)
		elif ext == "zip":
			return await source.save_series_zip(link)
		else:
			return await source.save_series(link)
	else:
		return await source.save_author(link)

