"""推荐指数：原始查表算法的等价实现与边界行为。"""

from __future__ import annotations

import math

import pytest

from policy.scoring import calculate_score


@pytest.mark.parametrize(
	("views", "bookmarks", "comments", "expected"),
	[
		(0, 0, 0, -0.75),
		(1, 1, 0, 6.5),
		(1, 1, 2, 7.5),
		(100, 8, 0, 3.5),
		(499, 40, 0, 3.5),
		(499, 50, 0, 6.5),
		(500, 45, 0, 6.0),
		(500, 50, 0, 7.5),
		(999, 100, 0, 7.5),
		(1000, 85, 0, 6.25),
		(1000, 90, 0, 7.0),
		(1001, 86, 0, 7.0),
		(2365, 203, 0, 9.0),
		(4000, 160, 0, 6.25),
		(4000, 180, 0, 7.0),
		(1000, 0, 1000, 3.47),
	],
)
def test_golden_cases(
	views: int,
	bookmarks: int,
	comments: int,
	expected: float,
) -> None:
	"""锁住原实现的输出，确保优化前后分数完全一致。"""
	assert calculate_score(views, bookmarks, comments) == expected


def test_returns_python_float() -> None:
	assert type(calculate_score(2365, 203)) is float


def test_caps() -> None:
	"""收藏率 10% 以上同分；4000 阅读以上同分（保持同一收藏率）。"""
	assert calculate_score(1000, 100) == calculate_score(1000, 1000)
	assert calculate_score(4000, 160) == calculate_score(100000, 4000)


def test_integer_bucket_matches_float_bucket() -> None:
	"""整数取档 (200*b)//v 必须等价于原实现的 int((100*b/v)//0.5)。"""
	for views in range(1, 2001):
		for bookmarks in (
			0,
			1,
			2,
			3,
			5,
			10,
			views // 20,
			views // 10,
			views,
			views * 2,
		):
			expected = min(int((100 * bookmarks / views) // 0.5), 20)
			assert min((200 * bookmarks) // views, 20) == expected


def test_bookmarks_are_non_decreasing() -> None:
	"""同一阅读量下，收藏增加不会让分数下降。"""
	for views in (500, 1000, 2000, 4000):
		previous = calculate_score(views, 0)
		for bookmarks in range(1, min(views, 1000) + 1):
			current = calculate_score(views, bookmarks)
			assert current >= previous
			previous = current


def test_comment_term_is_log2() -> None:
	base = calculate_score(4000, 160)
	for comments in (1, 2, 3, 5, 10, 32, 100):
		expected = round(base + round(math.log2(comments), 2), 2)
		assert calculate_score(4000, 160, comments) == expected


def test_known_band_edges() -> None:
	"""原实现的几个已知断点：先锁住行为，改口径时再更新。"""
	assert calculate_score(1000, 84) == 5.5
	assert calculate_score(1001, 84) == 6.25
	assert calculate_score(3499, 160) == 5.0
	assert calculate_score(3500, 160) == 6.0
	assert calculate_score(3999, 160) == 5.25
	assert calculate_score(4000, 160) == 6.25
