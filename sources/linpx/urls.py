import re

from sources.linpx.config import BASE, API_BASE
from sources.linpx.config import NOVEL_PATTERN, SERIES_PATTERN, AUTHOR_PATTERN


def url_novel(novel_id: str | int) -> str:
	return f"{BASE}/pixiv/novel/{novel_id}"

def url_series(series_id: str | int) -> str:
	# return f"{API_BASE}/pixiv/series/{series_id}/cache"
	return f"https://www.pixiv.net/novel/series/{series_id}"

def url_author(user_id: str | int) -> str:
	return f"{BASE}/pixiv/user/{user_id}"


def url_novel_data(novel_id: str | int) -> str:
	return f"{API_BASE}/pixiv/novel/{novel_id}/cache"

def url_series_data(series_id: str | int) -> str:
	return f"{API_BASE}/pixiv/series/{series_id}/cache"

def url_author_data(user_id: str | int) -> str:
	return f"{API_BASE}/pixiv/user/{user_id}/cache"

def url_fav_user_data() -> str:
	return f"{API_BASE}/fav/user/cache"


def get_novel_id(link: str) -> str | None:
	m = re.compile(NOVEL_PATTERN, re.I).search(link)
	if m:
		return m.group(1)
	return None

def get_series_id(link: str) -> str | None:
	"""从文本中解析系列 ID"""
	m = re.compile(SERIES_PATTERN, re.I).search(link)
	if m:
		return m.group(1)
	return None

def get_author_id(link: str) -> str | None:
	"""从文本中解析系列 ID"""
	m = re.compile(AUTHOR_PATTERN, re.I).search(link)
	if m:
		return m.group(1)
	return None

def is_novel_link(link: str) -> bool:
	return get_novel_id(link) is not None

def is_series_link(link: str) -> bool:
	return get_series_id(link) is not None

def is_author_link(link: str) -> bool:
	return get_author_id(link) is not None

def is_linpx_link(link: str) -> bool:
	"""是否为可处理的单篇或系列链接。"""
	return is_novel_link(link) or is_series_link(link) or is_author_link(link)