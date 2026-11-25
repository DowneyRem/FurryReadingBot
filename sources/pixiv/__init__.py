from __future__ import annotations

from sources.base import Novel, Series, Author, NovelSource
from sources.utils import get_id
from sources.pixiv.client import PixivClient
from sources.pixiv.errors import PixivParseError
from sources.pixiv.parse import json_to_novel, json_to_series, json_to_author
from sources.pixiv.config import NOVEL_PATTERN, SERIES_PATTERN, AUTHOR_PATTERN


def _extract_id(link: str, pattern: str, kind: str) -> str:
	"""纯数字 ID 直接用；否则从文本里抓链接 ID，抓不到就算解析失败。"""
	if link.isdigit():
		return link
	found = get_id(link, pattern)
	if not found:
		raise PixivParseError(f"无法从文本中解析 Pixiv {kind} ID", raw=link)
	return found


class PixivSource(NovelSource):
	"""Pixiv 原站直链；Cookie 可选，R18 正文需要登录态。"""
	name = "Pixiv"

	def __init__(self, client: PixivClient | None = None) -> None:
		self.client = client or PixivClient()
	
	def is_novel_link(self, link: str) -> bool:
		return get_id(link, NOVEL_PATTERN) is not None
	
	def is_series_link(self, link: str) -> bool:
		return get_id(link, SERIES_PATTERN) is not None
	
	def is_author_link(self, link: str) -> bool:
		return get_id(link, AUTHOR_PATTERN) is not None
	
	def can_handle(self, link: str) -> bool:
		return self.is_novel_link(link) or self.is_series_link(link) or self.is_author_link(link)
	
	
	async def fetch_novel(self, link: str) -> Novel:
		novel_id = _extract_id(link, NOVEL_PATTERN, "小说")
		data = await self.client.get_novel(novel_id)
		return json_to_novel(data)


	async def fetch_series(self, link: str) -> Series:
		series_id = _extract_id(link, SERIES_PATTERN, "系列")
		series = json_to_series(await self.client.get_series(series_id))

		# 系列详情不带章节列表：content_titles 一次拿全 ID + 标题，比逐页拉正文省请求
		titles = await self.client.get_series_titles(series_id)
		series.novel_ids = [str(item.id) for item in titles]
		series.novel_titles = [str(item.title or "") for item in titles]
		if not series.total:
			series.total = len(series.novel_ids)

		# 系列接口不带点赞 / 阅读量，用首篇补齐；系列为空（刚建 / 作者清空）时没有首篇可抓
		if series.novel_ids:
			novel = await self.fetch_novel(series.novel_ids[0])
			series.like_count = novel.like_count
			series.read_count = novel.read_count
			series.comment_count = novel.comment_count

		return series


	async def fetch_author(self, link: str) -> Author:
		author_id = _extract_id(link, AUTHOR_PATTERN, "作者")
		# 资料（名字 / 头像 / 简介）和全部作品 ID 是两个接口，合并交给解析层
		profile = await self.client.get_author(author_id)
		works = await self.client.get_author_all(author_id)
		return json_to_author(profile, works)
	