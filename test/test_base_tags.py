"""数据模型层接线：`Novel/Series/Author` 构造即规范化标签。"""

from __future__ import annotations

import sources.tags as tags_module
from sources.base import Author, Novel, Series
from sources.tags import Vocabulary

NOVEL_FIELDS = dict(
	novel_id="1", novel_url="u", novel_title="t",
	series_id=None, series_url=None, series_title=None,
	author_id="2", author_url="au", author_name="a",
	caption="", content="", like_count=0, read_count=0, comment_count=0,
	create_date="",
)

SERIES_FIELDS = dict(
	novel_id="1", novel_url="u", novel_title="t",
	series_id="9", series_url="su", series_title="st",
	author_id="2", author_url="au", author_name="a",
)


def test_novel_normalizes_tags_on_construction() -> None:
	novel = Novel(**NOVEL_FIELDS, tags=["兽人", "ケモホモ"])
	assert novel.tags == ["Gay", "Furry"]
	assert "标签：#Gay #Furry" in str(novel)      # 文案读的也是规范标签


def test_series_normalizes_tags_on_construction() -> None:
	series = Series(**SERIES_FIELDS, tags=["獸人"])
	assert series.tags == ["Furry"]


def test_author_keeps_unrecognized_tags() -> None:
	"""词表认不出的写法原样保留（不丢来源信息），文案照常输出。"""
	author = Author(**SERIES_FIELDS, tags=["原创"])
	assert author.tags == ["原创"]
	assert "标签：#原创" in str(author)


def test_model_build_does_not_break_when_vocabulary_unavailable(
	monkeypatch,
) -> None:
	"""词表缺失 / 出错时构造不能失败：标签原样保留。"""

	def boom() -> Vocabulary:
		raise FileNotFoundError("data/tags.toml 不存在")

	monkeypatch.setattr(tags_module, "get_vocabulary", boom)
	novel = Novel(**NOVEL_FIELDS, tags=["兽人"])
	assert novel.tags == ["兽人"]


def test_novel_applies_rating_exclusion() -> None:
	"""SFW 与 R18 / R18G 互斥：模型构造时就已剔除，文案 / txt 不会自相矛盾。"""
	assert Novel(**NOVEL_FIELDS, tags=["SFW"]).tags == ["SFW"]
	assert Novel(**NOVEL_FIELDS, tags=["SFW", "R18"]).tags == ["R18"]
	assert Novel(**NOVEL_FIELDS, tags=["SFW", "R18G"]).tags == ["R18", "R18G"]
