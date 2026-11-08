import re
from sources.base import Series


def is_real_series(series: Series) -> bool:
	count = 0
	arabic_pattern = re.compile(r'\d+')
	chinese_pattern = re.compile(r'[零一二三四五六七八九十百千万亿两〇壹贰叁肆伍陆柒捌玖拾佰仟萬]+')
	
	for title in series.novel_titles:
		arabic_matches = arabic_pattern.findall(title)
		chinese_matches = chinese_pattern.findall(title)
		count += len(arabic_matches) + len(chinese_matches)
	return count >= series.total * 0.75

