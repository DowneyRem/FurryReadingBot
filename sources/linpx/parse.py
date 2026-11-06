from __future__ import annotations

import re
from sources.base import Novel
from sources.linpx.urls import url_novel
from sources.linpx.config import PATTERN


def extract_novel_id(text: str) -> str | None:
	text = (text or "").strip()
	if text.isdigit():
		return text
	m = re.compile(PATTERN, re.I).search(text)
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


def json_to_novel(data: dict) -> Novel:
    if not data or data.get("error"):
        raise ValueError(data.get("error") or "Linpx 返回错误或空数据")

    novel_id = str(data.get("id") or data.get("_id") or "")
    title = (data.get("title") or "").strip()
    author_id = str(data.get("userId") or "")
    author_name = (data.get("userName") or "").strip()
    content = data.get("content") or ""
    tags = list(data.get("tags") or [])
    desc = data.get("desc") or data.get("description") or ""
    create_date = data.get("createDate") or ""

    series_id = None
    series_title = None
    series = data.get("series")
    if isinstance(series, dict) and series.get("id"):
        series_id = str(series["id"])
        series_title = (series.get("title") or "").strip() or None
	    
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