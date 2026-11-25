from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from sources.base import Series


@dataclass(frozen=True)
class IdRule:
	"""一条 ID 提取规则：用哪条正则抓，失败提示里该资源叫什么。"""
	pattern: str
	label: str


def get_id(link: str, pattern: str) -> str | None:
	"""严格版：只从链接文本里抓 ID；纯数字不算链接，返回 None。"""
	m = re.compile(pattern, re.I).search(link)
	if m:
		return m.group(1)
	return None


def is_real_series(series: Series) -> bool:
	count = 0
	arabic_pattern = re.compile(r'\d+')
	chinese_pattern = re.compile(r'[零一二三四五六七八九十百千万亿两〇壹贰叁肆伍陆柒捌玖拾佰仟萬]+')
	
	for title in series.novel_titles:
		arabic_matches = arabic_pattern.findall(title)
		chinese_matches = chinese_pattern.findall(title)
		count += len(arabic_matches) + len(chinese_matches)
	return count >= series.total * 0.75

