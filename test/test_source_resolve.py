"""sources.resolve_link：单篇 ↔ 系列按动作需要互相归一。

`dn` 带系列链接下载单篇时要落到首章（`Series.novel_url`），
`dst` / `dsz` 带单篇链接下载系列时要落到所属系列（`Novel.series_url`）。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_source_resolve.py -q
"""

from __future__ import annotations

import asyncio

import sources
from sources.base import Novel, Series
from sources.pixiv import PixivSource


SERIES_LINK = "https://www.pixiv.net/novel/series/16747997"
FIRST_NOVEL_LINK = "https://www.pixiv.net/novel/show.php?id=29588541"


def run(coro):
	return asyncio.run(coro)


def make_series(**kwargs) -> Series:
	fields = dict(
		novel_id="29588541",
		novel_url=FIRST_NOVEL_LINK,
		novel_title="第一章",
		series_id="16747997",
		series_url=SERIES_LINK,
		series_title="系列名",
		author_id="15478020",
		author_url="https://www.pixiv.net/users/15478020",
		author_name="安怀烈先",
	)
	fields.update(kwargs)
	return Series(**fields)


def make_novel(**kwargs) -> Novel:
	fields = dict(
		novel_id="29588541",
		novel_url=FIRST_NOVEL_LINK,
		novel_title="第一章",
		series_id="16747997",
		series_url=SERIES_LINK,
		series_title="系列名",
		author_id="15478020",
		author_url="https://www.pixiv.net/users/15478020",
		author_name="安怀烈先",
		caption="",
		content="正文",
		tags=[],
		like_count=0,
		read_count=0,
		comment_count=0,
		create_date="",
	)
	fields.update(kwargs)
	return Novel(**fields)


def test_series_link_resolves_to_first_novel(monkeypatch) -> None:
	"""dn 带系列链接：取 Series 的首篇，不需要键盘额外传 ID。"""
	async def fetch_series(self, link: str):
		return make_series()

	monkeypatch.setattr(PixivSource, "fetch_series", fetch_series)

	assert run(sources.resolve_link(SERIES_LINK, "novel")) == FIRST_NOVEL_LINK


def test_novel_link_resolves_to_series(monkeypatch) -> None:
	"""dst / dsz 带单篇链接：仍按原规则落到所属系列。"""
	async def fetch_novel(self, link: str):
		return make_novel()

	monkeypatch.setattr(PixivSource, "fetch_novel", fetch_novel)

	assert run(sources.resolve_link(FIRST_NOVEL_LINK, "series")) == SERIES_LINK


def test_matching_kind_keeps_link() -> None:
	"""类型本来就对：原样返回，不多打一次请求。"""
	assert run(sources.resolve_link(SERIES_LINK, "series")) == SERIES_LINK


if __name__ == "__main__":
	print("请使用 pytest 运行：python -m pytest test/test_source_resolve.py -q")
