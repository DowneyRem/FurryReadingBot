from __future__ import annotations

import re
from sources.base import Novel
from sources.linpx.urls import url_novel
from sources.linpx.config import NOVEL_PATTERN
from utils.json import JsonDict


def extract_novel_id(text: str) -> str | None:
	text = (text or "").strip()
	if text.isdigit():
		return text
	m = re.compile(NOVEL_PATTERN, re.I).search(text)
	if m:
		return m.group(1)
	return None


def is_linpx_link(text: str) -> bool:
	t = (text or "").lower()
	if extract_novel_id(text):
		if any(x in t for x in ("linpx", "furrynovel.ink")):
			return True
		if text.strip().isdigit():
			return True
	return False


def json_to_novel(data: dict | JsonDict) -> Novel:
	data = JsonDict.from_obj(data)
	if not data or data.error:
		raise ValueError(data.error or "Linpx 返回错误或空数据")

	novel_id = str(data.id or data._id or "")
	title = (data.title or "").strip()
	author_id = str(data.userId or "")
	author_name = (data.userName or "").strip()
	content = data.content or ""
	tags = list(data.tags or [])
	desc = data.desc or data.description or ""
	create_date = data.createDate or ""

	series_id = None
	series_title = None
	series = data.series
	if isinstance(series, dict) and series.id:
		series_id = str(series.id)
		series_title = (series.title or "").strip() or None

	url = url_novel(novel_id)

	return Novel(
		id=novel_id,
		title=title,
		author_id=author_id,
		author_name=author_name,
		content=content,
		tags=tags,
		description=desc,
		series_id=series_id,
		series_title=series_title,
		source="linpx",
		url=url,
		create_date=create_date,
		raw=data,
	)