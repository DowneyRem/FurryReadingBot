from __future__ import annotations

from sources.base import Novel, Series, Author, NovelSource
from sources.utils import get_id
from sources.linpx import client
from sources.linpx.errors import LinpxParseError
from sources.linpx.parse import json_to_novel, json_to_series, json_to_author
from sources.linpx.config import AUTHOR, NOVEL, SERIES


class LinpxSource(NovelSource):
	name = "Linpx"
	parse_error = LinpxParseError
	
	def is_novel_link(self, link: str) -> bool:
		return get_id(link, NOVEL.pattern) is not None
	
	def is_series_link(self, link: str) -> bool:
		return get_id(link, SERIES.pattern) is not None
	
	def is_author_link(self, link: str) -> bool:
		return get_id(link, AUTHOR.pattern) is not None

	def can_handle(self, link: str) -> bool:
		return self.is_novel_link(link) or self.is_series_link(link) or self.is_author_link(link)


	async def fetch_novel(self, link: str) -> Novel:
		novel_id = self.require_id(link, NOVEL)
		data = await client.get_novel(novel_id)
		return json_to_novel(data)
	
	
	async def fetch_series(self, link: str) -> Series:
		series_id = self.require_id(link, SERIES)
		data = await client.get_series(series_id)
		series = json_to_series(data)
		# 系列接口不带阅读量，用首篇补齐；系列为空（作者清空 / 刚建）时没有首篇可抓
		if series.novel_url:
			novel = await self.fetch_novel(series.novel_url)
			series.like_count = novel.like_count
			series.read_count = novel.read_count
		return series
	
	
	async def fetch_author(self, link: str) -> Author:
		author_id = self.require_id(link, AUTHOR)
		data = await client.get_author(author_id)
		return json_to_author(data)
