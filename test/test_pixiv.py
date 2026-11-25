"""Pixiv 源：链接识别 / ID 解析 / fetch_* 组装与解析（不打真实网络）。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_pixiv.py -q

需要真实网络时先设环境变量（live 用例只取公开作品，不依赖 PIXIV_COOKIE）:
	$env:PIXIV_LIVE = "1"
"""

from __future__ import annotations

import asyncio
import os

import pytest

from sources import fetch, resolve_source
from sources.linpx import LinpxSource
from sources.pixiv import PixivSource
from sources.pixiv.errors import PixivNotFoundError, PixivParseError
from sources.pixiv.parse import json_to_author, json_to_novel, json_to_series
from utils.json import JsonDict


NOVEL_ID = "12345678"
SERIES_ID = "87654321"
AUTHOR_ID = "13572468"

NOVEL_LINK = f"https://www.pixiv.net/novel/show.php?id={NOVEL_ID}"
SERIES_LINK = f"https://www.pixiv.net/novel/series/{SERIES_ID}"
AUTHOR_LINK = f"https://www.pixiv.net/users/{AUTHOR_ID}"

LIVE = os.getenv("PIXIV_LIVE") == "1"
live = pytest.mark.skipif(not LIVE, reason="需要真实 Pixiv API：PIXIV_LIVE=1")


def run(coro):
	return asyncio.run(coro)


def _envelope(body):
	return {"error": False, "message": "", "body": body}


def _novel_body(**overrides):
	body = {
		"id": NOVEL_ID,
		"title": "夜阑龙吟",
		"userId": AUTHOR_ID,
		"userName": "嘿，小兄弟",
		"description": "简介第一行<br />简介第二行",
		"content": "正文",
		# 小说详情里的 tags 是 `{authorId, isLocked, tags: [{tag, ...}], writable}` 外壳
		"tags": {
			"authorId": AUTHOR_ID,
			"isLocked": False,
			"tags": [{"tag": "原创", "locked": True}],
			"writable": False,
		},
		"bookmarkCount": 12,
		"viewCount": 345,
		"commentCount": 6,
		"seriesNavData": None,
		"coverUrl": "https://i.pximg.net/cover.jpg",
		"createDate": "2026-01-02T03:04:05+09:00",
		"language": "zh-cn",
	}
	body.update(overrides)
	return body


def _series_body(**overrides):
	body = {
		"id": SERIES_ID,
		"title": "系列名",
		"caption": "系列简介",
		"userId": AUTHOR_ID,
		"userName": "嘿，小兄弟",
		"firstNovelId": "1001",
		"publishedContentCount": 2,
		"tags": ["原创"],
	}
	body.update(overrides)
	return body


def _profile_body(**overrides):
	body = {
		"userId": AUTHOR_ID,
		"name": "嘿，小兄弟",
		"image": "https://i.pximg.net/user.jpg",
		"comment": "作者简介<br />第二行",
	}
	body.update(overrides)
	return body


def _works_body(**overrides):
	body = {
		"novels": {"1001": None, "1002": None},
		"novelSeries": [{"id": SERIES_ID, "title": "系列名"}],
	}
	body.update(overrides)
	return body


class FakeClient:
	"""只实现 source 用到的 5 个方法，返回固定 envelope，并记录调用顺序。"""

	def __init__(self) -> None:
		self.calls: list[tuple[str, str]] = []
		self.novel = _envelope(_novel_body())
		self.series = _envelope(_series_body())
		self.titles = [{"id": "1001", "title": "第一章"}, {"id": "1002", "title": "第二章"}]
		self.profile = _envelope(_profile_body())
		self.works = _envelope(_works_body())

	async def get_novel(self, novel_id):
		self.calls.append(("novel", str(novel_id)))
		return JsonDict.from_obj(self.novel)

	async def get_series(self, series_id):
		self.calls.append(("series", str(series_id)))
		return JsonDict.from_obj(self.series)

	async def get_series_titles(self, series_id):
		self.calls.append(("titles", str(series_id)))
		return [JsonDict.from_obj(item) for item in self.titles]

	async def get_author(self, author_id):
		self.calls.append(("author", str(author_id)))
		return JsonDict.from_obj(self.profile)

	async def get_author_works(self, author_id):
		self.calls.append(("works", str(author_id)))
		return JsonDict.from_obj(self.works)


def _source() -> tuple[PixivSource, FakeClient]:
	client = FakeClient()
	return PixivSource(client=client), client


def test_can_handle() -> None:
	src, _ = _source()
	assert src.can_handle(NOVEL_LINK) is True
	assert src.can_handle(SERIES_LINK) is True
	assert src.can_handle(AUTHOR_LINK) is True
	assert src.can_handle(NOVEL_ID) is False  # 纯数字 ID 不是链接，先归一化再进来
	assert src.can_handle("不是链接") is False


def test_registered_in_sources() -> None:
	"""接入 bot：`resolve_source` 用注册表里的实例认出 Pixiv 三类链接。"""
	for link in (NOVEL_LINK, SERIES_LINK, AUTHOR_LINK):
		assert isinstance(resolve_source(link), PixivSource)
	# 顺序不影响：Linpx 链接仍然归 Linpx
	linpx = f"https://linpx.ink/pixiv/novel/{NOVEL_ID}"
	assert isinstance(resolve_source(linpx), LinpxSource)


def test_fetch_novel_accepts_link_and_id() -> None:
	src, client = _source()

	novel = run(src.fetch_novel(NOVEL_LINK))

	assert novel.id == NOVEL_ID
	assert novel.title == "夜阑龙吟"
	assert novel.author_url == f"https://www.pixiv.net/users/{AUTHOR_ID}"
	assert novel.series_id is None  # 单篇没有 seriesNavData，不能因此崩掉
	assert novel.caption == "简介第一行\n简介第二行"
	assert novel.tags == ["原创"]
	assert novel.like_count == 12
	assert client.calls == [("novel", NOVEL_ID)]

	# 打包系列 / 作者时是按纯数字 ID 拉章节的
	assert run(src.fetch_novel(NOVEL_ID)).id == NOVEL_ID


def test_fetch_novel_rejects_text_without_link() -> None:
	src, client = _source()
	with pytest.raises(PixivParseError):
		run(src.fetch_novel("随便一段话"))
	assert client.calls == []


def test_fetch_series_fills_chapters_and_counts() -> None:
	src, client = _source()

	series = run(src.fetch_series(SERIES_LINK))

	assert series.id == SERIES_ID
	assert series.title == "系列名"
	assert series.novel_ids == ["1001", "1002"]
	assert series.novel_titles == ["第一章", "第二章"]
	assert series.total == 2
	# 系列接口不带点赞 / 阅读量，用首篇补齐
	assert series.like_count == 12
	assert series.read_count == 345
	assert client.calls == [
		("series", SERIES_ID),
		("titles", SERIES_ID),
		("novel", "1001"),
	]


def test_fetch_author_merges_profile_and_works() -> None:
	src, client = _source()

	author = run(src.fetch_author(AUTHOR_LINK))

	assert author.id == AUTHOR_ID
	assert author.title == "嘿，小兄弟"
	assert author.novel_ids == ["1001", "1002"]
	assert author.series_ids == [SERIES_ID]
	assert author.comment == "作者简介\n第二行"
	assert author.image_url == "https://i.pximg.net/user.jpg"
	assert client.calls == [("author", AUTHOR_ID), ("works", AUTHOR_ID)]


def test_json_to_novel_fills_series_from_series_nav() -> None:
	"""单篇属于系列时，seriesNavData 提供 ID / 标题，下载菜单才能给出「下载系列」。"""
	novel = json_to_novel(_envelope(_novel_body(seriesNavData={
		"seriesType": "novel", "seriesId": int(SERIES_ID), "title": "系列名"})))

	assert str(novel.series_id) == SERIES_ID
	assert novel.series_url == f"https://www.pixiv.net/novel/series/{SERIES_ID}"
	assert novel.series_title == "系列名"


def test_json_to_novel_missing_body() -> None:
	with pytest.raises(PixivNotFoundError):
		json_to_novel(_envelope(None))
	with pytest.raises(PixivNotFoundError):
		json_to_novel({"error": True, "message": "作品不存在", "body": None})


def test_json_to_novel_tolerates_missing_text_fields() -> None:
	"""缺标题 / 作者名 / 正文时补空串：别把 None 带进文件名、文案和缓存。"""
	novel = json_to_novel(_envelope(_novel_body(
		title=None, userName=None, content=None)))
	assert novel.title == ""
	assert novel.author_name == ""
	assert novel.content == ""


def test_json_to_series_allows_empty_series() -> None:
	# 作者清空 / 刚建的系列：没有首篇，total 也拿不到
	series = json_to_series(_envelope(_series_body(
		firstNovelId=None, publishedContentCount=None)))
	assert series.novel_id == ""
	assert series.novel_url == ""
	assert series.total == 0


def test_json_to_author_without_works() -> None:
	author = json_to_author(_envelope(_profile_body()))
	assert author.novel_ids == []
	assert author.series_ids == []
	assert author.series_id is None


def test_json_to_author_missing_profile() -> None:
	with pytest.raises(PixivNotFoundError):
		json_to_author(_envelope(None))


@live
def test_live_fetch_public_novel() -> None:
	"""公开作品：走注册表 → Pixiv client → 解析，正文不应为空。"""
	novel = run(fetch("https://www.pixiv.net/novel/show.php?id=29588542"))
	assert novel.id == "29588542"
	assert novel.title
	assert novel.content
	assert novel.author_id
	assert novel.source == "Pixiv"


@live
def test_live_fetch_public_series() -> None:
	series = run(fetch("https://www.pixiv.net/novel/series/16181401"))
	assert series.id == "16181401"
	assert series.novel_ids
	assert series.total == len(series.novel_ids)
	assert series.title


if __name__ == "__main__":
	print("请使用 pytest 运行：python -m pytest test/test_pixiv.py -q")
