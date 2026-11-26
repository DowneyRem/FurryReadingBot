"""ID 规则与提取：IdRule 绑定 pattern/label，get_id 兼容纯数字与链接。

外加时间工具：冷却的剩余秒数、TTL 判定（`is_expired` / `is_older_than`），
它们是 `storage/` 里全部过期判断的唯一实现。
"""

from __future__ import annotations

from datetime import timedelta

from sources.linpx.config import NOVEL as LINPX_NOVEL
from sources.linpx.config import NOVEL_PATTERN as LINPX_NOVEL_PATTERN
from sources.pixiv.config import NOVEL as PIXIV_NOVEL
from sources.pixiv.config import NOVEL_PATTERN as PIXIV_NOVEL_PATTERN
from sources.utils import get_id
from utils.json import to_int, to_str
from utils.time import (
	cooldown_left,
	cooldown_remaining,
	is_expired,
	is_older_than,
	remaining_seconds,
	utc_now,
)


def _iso(delta: timedelta) -> str:
	return (utc_now() + delta).strftime("%Y-%m-%dT%H:%M:%S%z")


def test_to_int_and_to_str_normalise_fields() -> None:
	"""存储读盘用的宽松转换：坏值不炸，None → 0 / ""。"""
	assert to_int(None) == 0
	assert to_int("12") == 12
	assert to_int(3.9) == 3
	assert to_int("不是数字") == 0
	assert to_str(None) == ""
	assert to_str(42) == "42"
	assert to_str(0) == "0"


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


def test_cooldown_left_reads_stamp() -> None:
	"""冷却判定直接吃存储里的时间字符串：缺失 / 坏值 / 已过期都是 0。"""
	assert cooldown_left(_iso(timedelta(hours=-25)), 24) == 0.0
	assert 0 < cooldown_left(_iso(timedelta(hours=-1)), 24) <= 24 * 3600
	assert cooldown_left("", 24) == 0.0
	assert cooldown_left("不是时间", 24) == 0.0
	assert cooldown_left(_iso(timedelta(hours=-1)), 0) == 0.0


def test_remaining_seconds_takes_any_window() -> None:
	"""同一套减法：窗口单位由调用方给（分钟 / 小时 / 天）。"""
	assert remaining_seconds(None, timedelta(hours=1)) == 0.0
	assert remaining_seconds(utc_now() - timedelta(hours=2), timedelta(hours=1)) == 0.0
	assert 0 < remaining_seconds(utc_now(), timedelta(minutes=30)) <= 30 * 60
	assert 0 < remaining_seconds(utc_now(), timedelta(days=3)) <= 3 * 86400


def test_is_expired_reads_absolute_stamp() -> None:
	"""expires_at 判定：到期 / 未到期，解析失败时看 missing 开关。"""
	assert is_expired(_iso(timedelta(hours=-1))) is True
	assert is_expired(_iso(timedelta(hours=1))) is False
	assert is_expired(_iso(timedelta(0))) is True
	# 缺失：缓存要重建（missing=True），业务数据保留（默认 False）
	assert is_expired("", missing=True) is True
	assert is_expired("不是时间", missing=True) is True
	assert is_expired("") is False
	assert is_expired("不是时间") is False
	# 同一批淘汰可以共用同一个 now
	assert is_expired(_iso(timedelta(hours=1)), now=utc_now()) is False


def test_is_older_than_ttl() -> None:
	"""业务时间 + TTL 天数：时间缺失不淘汰，0 天 = 过去的都算过期。"""
	assert is_older_than(None, 1) is False
	assert is_older_than(utc_now() - timedelta(days=2), 1) is True
	assert is_older_than(utc_now() - timedelta(days=1, hours=23), 2) is False
	assert is_older_than(utc_now(), 0) is True
