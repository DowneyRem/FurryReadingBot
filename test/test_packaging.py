"""打包：命名、同名不覆盖、失败不残留、作者全量布局。

运行（在项目根目录）:
	python -m pytest test/test_packaging.py -q
"""

from __future__ import annotations

import asyncio
import zipfile

import pytest

from services import packaging
from sources.base import Author, Novel, NovelSource, Series


SERIES_LINK = "src://series/1"
AUTHOR_LINK = "src://author/9"
NOVEL_LINK = "src://novel/1"


def novel(novel_id: str, title: str, author_name: str = "作者") -> Novel:
	return Novel(
		novel_id=novel_id, novel_url=f"src://novel/{novel_id}", novel_title=title,
		series_id=None, series_url=None, series_title=None,
		author_id="9", author_url=AUTHOR_LINK, author_name=author_name,
		caption="", content=f"正文{novel_id}", like_count=0, read_count=0, create_date="",
	)


def series(series_id: str, title: str, novels: list[Novel]) -> Series:
	return Series(
		novel_id=novels[0].novel_id if novels else "", novel_url="", novel_title="",
		series_id=series_id, series_url=f"src://series/{series_id}", series_title=title,
		author_id="9", author_url=AUTHOR_LINK, author_name="作者",
		total=len(novels),
		novel_ids=[n.novel_id for n in novels],
		novel_titles=[n.novel_title for n in novels],
	)


class FakeSource(NovelSource):
	name = "fake"

	def __init__(self, *, novels=(), series_list=(), author=None, fail_on=None):
		self.novels = {n.novel_id: n for n in novels}
		self.series = {s.series_id: s for s in series_list}
		self.author = author
		self.fail_on = fail_on

	def is_novel_link(self, link): return "/novel/" in link
	def is_series_link(self, link): return "/series/" in link
	def is_author_link(self, link): return "/author/" in link
	def can_handle(self, link): return link.startswith("src://")

	async def fetch_novel(self, link):
		novel_id = link.rsplit("/", 1)[-1]
		if novel_id == self.fail_on:
			raise RuntimeError("network down")
		return self.novels[novel_id]

	async def fetch_series(self, link):
		return self.series[link.rsplit("/", 1)[-1]]

	async def fetch_author(self, link):
		return self.author


@pytest.fixture
def use_source(monkeypatch):
	def install(source: FakeSource) -> None:
		monkeypatch.setattr(packaging, "resolve_source", lambda link: source)
	return install


def build(link, file_type, work_root):
	return asyncio.run(packaging.build(link, file_type, work_root=work_root))


def zip_names(path) -> list[str]:
	with zipfile.ZipFile(path) as z:
		return sorted(z.namelist())


def test_series_zip_keeps_same_title_chapters_in_order(tmp_path, use_source) -> None:
	chapters = [novel("1", "续"), novel("2", "续"), novel("3", "终章")]
	use_source(FakeSource(novels=chapters, series_list=[series("1", "长篇", chapters)]))

	path = build(SERIES_LINK, "zip", tmp_path)

	assert zip_names(path) == ["长篇/1_续.txt", "长篇/2_续.txt", "长篇/3_终章.txt"]


def test_names_with_separators_stay_inside_workdir(tmp_path, use_source) -> None:
	chapters = [novel("1", "../逃逸", author_name="/etc")]
	author = Author(
		novel_id="1", novel_url="", novel_title="",
		series_id=None, series_url=None, series_title=None,
		author_id="9", author_url=AUTHOR_LINK, author_name="/etc",
		novel_ids=["1"],
	)
	use_source(FakeSource(novels=chapters, author=author))

	path = build(AUTHOR_LINK, "zip", tmp_path)

	assert path.resolve().is_relative_to(tmp_path.resolve())
	assert zip_names(path) == ["etc/单篇/逃逸.txt"]


def test_author_layout_and_same_title_series(tmp_path, use_source) -> None:
	a = [novel("1", "上"), novel("2", "下")]
	b = [novel("3", "甲"), novel("4", "乙")]
	single = novel("5", "短篇")
	author = Author(
		novel_id="1", novel_url="", novel_title="",
		series_id=None, series_url=None, series_title=None,
		author_id="9", author_url=AUTHOR_LINK, author_name="作者",
		novel_ids=["1", "2", "3", "4", "5"], series_ids=["10", "11"],
	)
	use_source(FakeSource(
		novels=[*a, *b, single],
		series_list=[series("10", "同名", a), series("11", "同名", b)],
		author=author,
	))

	path = build(AUTHOR_LINK, "zip", tmp_path)

	assert zip_names(path) == [
		"作者/单篇/短篇.txt",
		"作者/同名 (2)/1_甲.txt",
		"作者/同名 (2)/2_乙.txt",
		"作者/同名/1_上.txt",
		"作者/同名/2_下.txt",
	]


def test_failure_leaves_no_files(tmp_path, use_source) -> None:
	chapters = [novel("1", "一"), novel("2", "二")]
	use_source(FakeSource(
		novels=chapters, series_list=[series("1", "长篇", chapters)], fail_on="2"))

	with pytest.raises(RuntimeError):
		build(SERIES_LINK, "zip", tmp_path)

	assert list(tmp_path.iterdir()) == []


def test_discard_removes_whole_workdir(tmp_path, use_source) -> None:
	use_source(FakeSource(novels=[novel("1", "单篇")]))

	path = build(NOVEL_LINK, "txt", tmp_path)
	asyncio.run(packaging.discard(path, work_root=tmp_path))

	assert list(tmp_path.iterdir()) == []
