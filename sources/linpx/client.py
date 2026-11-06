from __future__ import annotations

from storage.file_async import get_json
from sources.linpx.urls import url_novel_data, url_series_data, url_user_data
from sources.linpx.config import HEADERS
from utils.json import JsonDict


async def get_novel(novel_id: str | int) -> JsonDict:
	data = await get_json(url_novel_data(novel_id), headers=HEADERS)
	return JsonDict.from_obj(data)


async def get_series(series_id: str | int) -> JsonDict:
	data = await get_json(url_series_data(series_id), headers=HEADERS)
	return JsonDict.from_obj(data)


async def get_user(user_id: str | int) -> JsonDict:
	data = await get_json(url_user_data(user_id), headers=HEADERS)
	return JsonDict.from_obj(data)
