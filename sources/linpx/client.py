from __future__ import annotations

from infra.http import HttpError, get_json
from sources.linpx.urls import url_novel_data, url_series_data, url_author_data
from sources.linpx.config import HEADERS
from sources.linpx.errors import LinpxNetworkError
from utils.json import JsonDict


async def _get(url: str) -> JsonDict:
	"""请求 Linpx 接口；404 视为没有数据，交给解析层报「不存在」，其余失败报网络错误。"""
	try:
		data = await get_json(url, headers=HEADERS)
	except HttpError as e:
		if e.status == 404:
			return JsonDict()
		raise LinpxNetworkError("Linpx 暂时无法访问，请稍后重试", raw=e.url) from e
	return JsonDict.from_obj(data)


async def get_novel(novel_id: str | int) -> JsonDict:
	return await _get(url_novel_data(novel_id))


async def get_series(series_id: str | int) -> JsonDict:
	return await _get(url_series_data(series_id))


async def get_author(user_id: str | int) -> JsonDict:
	return await _get(url_author_data(user_id))
