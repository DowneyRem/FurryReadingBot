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


async def fetch_novel(link: str) -> Novel:
	return await resolve_source(link).fetch_novel(link)

async def fetch_series(link: str) -> Series:
	return await resolve_source(link).fetch_series(link)

async def fetch_author(link: str) -> Author:
	return await resolve_source(link).fetch_author(link)


async def save_novel(link: str) -> Path:
	return Path(await resolve_source(link).save_novel(link))

async def save_series(link: str) -> Path:
	return Path(await resolve_source(link).save_series(link))

async def save_series_txt(link: str) -> Path:
	return Path(await resolve_source(link).save_series_txt(link))

async def save_series_zip(link: str) -> Path:
	return Path(await resolve_source(link).save_series_zip(link))

async def save_author(link: str) -> Path:
	return Path(await resolve_source(link).save_author(link))
