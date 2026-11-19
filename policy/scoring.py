"""推荐指数：原始查表算法的等价实现。
todo 优化 评分规则：：
    score = -7.75 + min(views // 500, 8) + 0.75 * min(rate // 0.5, 20)
    rate  = 100 * bookmarks / views
    comments >= 1 时，score += round(log2(comments), 2)
    views <= 1000 时，score += -0.75
    最终 round(score, 2)
"""

from __future__ import annotations

import math

# 原始 9×21 表的参数
BASE_SCORE = -7.75
VIEWS_PER_ROW = 500
MAX_VIEWS_ROW = 8          # 4000 阅读封顶
MAX_RATE_COLUMN = 20       # 10% 收藏率封顶
SCORE_PER_COLUMN = 0.75
LOW_VIEWS_LIMIT = 1000
LOW_VIEWS_PENALTY = -0.75


def calculate_score(views: int, bookmarks: int, comments: int = 0) -> float:
	score = 0.0
	if views:
		row = min(views // VIEWS_PER_ROW, MAX_VIEWS_ROW)
		# 原实现是 int((100 * bookmarks / views) // 0.5)；
		# 用整数写法避免浮点边界误差，数学上等价于 floor(rate / 0.5)。
		column = min((200 * bookmarks) // views, MAX_RATE_COLUMN)
		score = BASE_SCORE + row + SCORE_PER_COLUMN * column

	if comments >= 1:
		score += round(math.log2(comments), 2)

	if views <= LOW_VIEWS_LIMIT:
		score += LOW_VIEWS_PENALTY

	return round(score, 2)
