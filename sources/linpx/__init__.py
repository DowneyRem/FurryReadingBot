from __future__ import annotations

from sources.base import Novel, Series, Author, NovelSource
from sources.utils import get_id
from sources.linpx import client
from sources.linpx.errors import LinpxParseError
from sources.linpx.parse import json_to_novel, json_to_series, json_to_author
from sources.linpx.config import NOVEL_PATTERN, SERIES_PATTERN, AUTHOR_PATTERN


class LinpxSource(NovelSource):
	name = "linpx"
	
	def is_novel_link(self, link: str) -> bool:
		return get_id(link, NOVEL_PATTERN) is not None
	
	def is_series_link(self, link: str) -> bool:
		return get_id(link, SERIES_PATTERN) is not None
	
	def is_author_link(self, link: str) -> bool:
		return get_id(link, AUTHOR_PATTERN) is not None

	def can_handle(self, link: str) -> bool:
		return self.is_novel_link(link) or self.is_series_link(link) or self.is_author_link(link)


	async def fetch_novel(self, link: str) -> Novel:
		if link.isdigit():
			novel_id = link
		else:
			novel_id = get_id(link, NOVEL_PATTERN)
			if not novel_id:
				raise LinpxParseError("无法从文本中解析 Linpx 小说 ID", raw=link)
			
		data = await client.get_novel(novel_id)
		return json_to_novel(data)
	
	
	async def fetch_series(self, link: str) -> Series:
		if link.isdigit():
			series_id = link
		else:
			series_id = get_id(link, SERIES_PATTERN)
			if not series_id:
				raise LinpxParseError("无法从文本中解析 Linpx 系列 ID", raw=link)
		
		data = await client.get_series(series_id)
		return json_to_series(data)
	
	
	async def fetch_author(self, link: str) -> Author:
		if link.isdigit():
			author_id = link
		else:
			author_id = get_id(link, AUTHOR_PATTERN)
			if not author_id:
				raise LinpxParseError("无法从文本中解析 Linpx 作者 ID", raw=link)
		
		data = await client.get_author(author_id)
		return json_to_author(data)
