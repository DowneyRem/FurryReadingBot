"""ID 规则与提取：IdRule 绑定 pattern/label，get_id 兼容纯数字与链接。

外加时间工具：申请冷却的剩余秒数计算。
"""

from __future__ import annotations

from datetime import timedelta

from sources.linpx.config import NOVEL as LINPX_NOVEL
from sources.linpx.config import NOVEL_PATTERN as LINPX_NOVEL_PATTERN
from sources.pixiv.config import NOVEL as PIXIV_NOVEL
from sources.pixiv.config import NOVEL_PATTERN as PIXIV_NOVEL_PATTERN
from sources.utils import get_id
from utils.time import cooldown_remaining, utc_now


def test_id_rule_binds_pattern_and_label() -> None:
	assert PIXIV_NOVEL.pattern == PIXIV_NOVEL_PATTERN
	assert LINPX_NOVEL.pattern == LINPX_NOVEL_PATTERN
	assert PIXIV_NOVEL.label == "小说"
	assert LINPX_NOVEL.label == "小说"


def test_raw_id_is_not_a_link() -> None:
	"""get_id 是严格版：只认链接；纯数字走 require_id 的宽松分支。"""
	assert get_id("18012577", LINPX_NOVEL_PATTERN) is None
	assert get_id("12345678", PIXIV_NOVEL_PATTERN) is None


def test_extracts_from_link() -> None:
	link = "https://linpx.ink/pixiv/novel/18012577"
	assert get_id(link, LINPX_NOVEL_PATTERN) == "18012577"


def test_extracts_from_sentence() -> None:
	text = "请下载这篇 https://www.pixiv.net/novel/show.php?id=12345678 谢谢"
	assert get_id(text, PIXIV_NOVEL_PATTERN) == "12345678"


def test_returns_none_without_id() -> None:
	assert get_id("hello world", LINPX_NOVEL_PATTERN) is None
	assert get_id("", PIXIV_NOVEL_PATTERN) is None


def test_cooldown_remaining_counts_down() -> None:
	"""申请冷却：时间缺失 / 已过期都是 0，窗口内返回剩余秒数。"""
	assert cooldown_remaining(None, 24) == 0.0
	assert cooldown_remaining(utc_now() - timedelta(hours=25), 24) == 0.0
	assert 0 < cooldown_remaining(utc_now(), 24) <= 24 * 3600
	assert cooldown_remaining(utc_now(), 0) == 0.0
