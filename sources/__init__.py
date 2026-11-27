from __future__ import annotations

from sources.base import Author, Novel, NovelSource, Series
from sources.linpx import LinpxSource
from sources.pixiv import PixivSource


# 注册顺序 = 匹配优先级；两家的链接域名不重叠，顺序只影响将来兼容别名的场景。
# Pixiv 原站链接（pixiv.net）与 Linpx 代理链接（linpx.ink / furrynovel.ink）指向同一批作品，
# ID 也是同一套，所以缓存 / 名单 / 分享记录天然互通。
_SOURCES: list[NovelSource] = [
	LinpxSource(),
	PixivSource(),
]


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
	"""按动作需要的类型归一链接：单篇要系列时换成系列，系列要单篇时换成首章。"""
	source = _require_source(link)
	if kind == "series" and source.is_novel_link(link):
		novel = await source.fetch_novel(link)
		return novel.series_url or link
	if kind == "novel" and source.is_series_link(link):
		# 「📄 下载首章」直接带系列链接：系列模型的首篇字段就是第一章
		series = await source.fetch_series(link)
		return series.novel_url or link
	return link
